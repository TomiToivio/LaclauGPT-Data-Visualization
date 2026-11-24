"""Category-specific matching rules and the clustering that applies them (#300).

The hard part of label merging is not string distance, it is that the same distance means
different things in different categories:

* ``Petteri Orpo`` / ``PM Orpo`` / ``Orpo`` are one person — but ``Orpo`` is also how you name
  whichever Orpo the corpus happens to contain, so a bare surname merges only when exactly one
  full name in the corpus could be meant. Otherwise it is a review candidate.
* ``Social Europe`` and ``Arguments for Europe`` share the word *Europe* and are different
  themes. Themes and topics therefore need token-set near-equality, not containment.
* ``good housing policy`` under *positive* and under *negative* is one phrase with two meanings.
  Polarity is part of the identity, so sentiment never merges across it.

Everything returns explicit ``Cluster`` / ``ReviewCandidate`` records: a merge the script is not
sure about is never applied silently.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from itertools import combinations

from .model import Cluster, LabelStat, MergeResult, ReviewCandidate
from .normalization import (
    Normalized,
    clean_label,
    normalize_label,
    strip_leading_article,
)

#: Party names the EP24 corpus writes several ways. This is a *curated* list, not a heuristic:
#: each entry is a decision a researcher could have made by hand, it only applies to entity
#: labels, and every merge it causes still appears in the review queue and in the exported
#: mapping. A bare "Christian Democrats" is only the German CDU when the corpus says the mention
#: is German — the Netherlands, Belgium and others have their own Christian democratic parties.
PARTY_ALIASES: dict[str, str] = {
    "true finns": "perussuomalaiset",
    "finns party": "perussuomalaiset",
    "the finns party": "perussuomalaiset",
    "cdu christian democrats": "cdu",
    "christian democratic union": "cdu",
    "cdu": "cdu",
}

GERMAN_COUNTRIES: frozenset[str] = frozenset({"de", "deu", "germany", "deutschland"})

#: How the canonical party names are written. The alias table works on folded text, so without
#: this "CDU" would come back as "cdu" and every party label would look like a rename.
PARTY_DISPLAY: dict[str, str] = {
    "perussuomalaiset": "Perussuomalaiset",
    "cdu": "CDU",
}


def party_alias(folded: str, countries: tuple[str, ...]) -> str:
    """The canonical party name for a folded label, or the label unchanged."""
    if folded in PARTY_ALIASES:
        return PARTY_ALIASES[folded]
    if folded == "christian democrats" and countries and all(
        country.casefold() in GERMAN_COUNTRIES for country in countries
    ):
        return "cdu"
    return folded


#: Above this many labels, a shared token says nothing and only costs comparisons.
MAX_BUCKET = 150

#: How many alternatives one review row may show. More than this is a search result, not a choice.
MAX_ALTERNATIVES = 4


@dataclass(frozen=True)
class CategoryRule:
    """How one category decides that two labels are the same thing."""

    name: str
    strip_titles: bool = False
    strip_legal_suffixes: bool = False
    #: Whether a parenthetical is a gloss to drop ("Union (EBU)") or content to keep
    #: ("elections (2024)"). True for entities and people only.
    strip_parentheticals: bool = False
    #: Score at or above which two labels may be joined automatically.
    auto_merge: float = 0.90
    #: Score at or above which a pair is worth a researcher's attention.
    review: float = 0.75
    #: Whether a one-token label may join the single full name that contains it.
    surname_merge: bool = False
    #: Containment counts as identity (person/org) or not (theme/topic/sentiment).
    containment_is_identity: bool = True
    #: How many extra words a containing label may add and still be the same thing: one covers
    #: "the European Union" and a middle name, not "European Union and its member states".
    containment_slack: int = 1
    #: Whether those extra words may be content words. True for people (a middle name is not
    #: optional information), false for organisations: "European Union parliament" is a different
    #: referent, not another spelling of the union.
    containment_allows_content: bool = False

    def normalize(self, label: str) -> Normalized:
        return normalize_label(
            label,
            strip_titles=self.strip_titles,
            strip_legal_suffixes=self.strip_legal_suffixes,
            strip_parentheticals=self.strip_parentheticals,
        )


#: The five categories of #300. The thresholds are deliberately conservative: a wrong merge
#: silently corrupts every count downstream, while a missed merge costs one review card.
RULES: dict[str, CategoryRule] = {
    "person": CategoryRule(
        name="person",
        strip_titles=True,
        strip_parentheticals=True,
        auto_merge=0.90,
        review=0.80,
        surname_merge=True,
        containment_allows_content=True,
    ),
    "entity": CategoryRule(
        name="entity",
        strip_legal_suffixes=True,
        strip_parentheticals=True,
        auto_merge=0.92,
        review=0.85,
        surname_merge=False,
    ),
    "theme": CategoryRule(
        name="theme",
        auto_merge=0.90,
        review=0.82,
        containment_is_identity=False,
    ),
    "topic": CategoryRule(
        name="topic",
        auto_merge=0.90,
        review=0.82,
        containment_is_identity=False,
    ),
    "sentiment": CategoryRule(
        name="sentiment",
        auto_merge=0.92,
        review=0.85,
        containment_is_identity=False,
    ),
}


def _ratio(left: str, right: str) -> float:
    return SequenceMatcher(a=left, b=right, autojunk=False).ratio()


def similarity(left: Normalized, right: Normalized, rule: CategoryRule) -> tuple[float, str]:
    """Score two labels for *this* category, and name the relation that produced the score."""
    if not left.core_tokens or not right.core_tokens:
        return 0.0, "empty"
    if left.key == right.key:
        # Same words, possibly another order ("Orpo Petteri"). The only relation that is
        # identity by itself.
        return 1.0, "token-set"
    left_set, right_set = set(left.core_tokens), set(right.core_tokens)
    if rule.containment_is_identity and (left_set < right_set or right_set < left_set):
        shorter, longer = (left, right) if len(left.core_tokens) < len(right.core_tokens) else (
            right,
            left,
        )
        # Containment is only identity when the shorter label is *the same phrase* with words
        # added: contiguous, and few. "European Union" is inside "European Broadcasting Union
        # (EBU)" as a set of tokens but not as a phrase, and merging those two renamed 3 885
        # occurrences of one entity to the other.
        extras = [token for token in longer.core_tokens if token not in set(shorter.core_tokens)]
        if (
            _contiguous_in(shorter.core_tokens, longer.core_tokens)
            and len(extras) <= rule.containment_slack
            and (rule.containment_allows_content or _extras_are_neutral(extras, shorter.core_tokens))
        ):
            # "orpo" inside "petteri orpo": strong evidence, but the caller has to establish that
            # only one such full name exists before this may merge (see `_surname_pair_ok`).
            return (0.93, "surname") if len(shorter.core_tokens) == 1 else (0.94, "containment")
    # Themes, topics and sentiment targets: near-equality, never containment — "Europe" is a
    # shared word, not a shared meaning.
    return _ratio(left.core, right.core), "ratio"


#: Words that add no referent: an article or a conjunction around a name is the same name.
ARTICLES: frozenset[str] = frozenset({"the", "a", "an", "of", "and", "for", "in", "on", "at", "to"})


def _extras_are_neutral(extras: list[str], base: tuple[str, ...]) -> bool:
    """Are the added words articles, or an acronym of what they are attached to?

    ``EU`` is an acronym of *European Union*, so "EU European Union" is one entity; *parliament*
    is a content word and makes "European Union parliament" a different referent.
    """
    initials = "".join(token[0] for token in base)
    for token in extras:
        if token in ARTICLES:
            continue
        if len(token) <= len(initials) and initials.startswith(token):
            continue
        return False
    return True


def _contiguous_in(shorter: tuple[str, ...], longer: tuple[str, ...]) -> bool:
    """Is ``shorter`` one unbroken run of words inside ``longer``?"""
    span = len(shorter)
    return any(
        longer[index : index + span] == shorter
        for index in range(len(longer) - span + 1)
    )


def _acronym_noise(item: Normalized) -> int:
    """How many of this label's own tokens are just an acronym of the others.

    "spd social democratic party" and "social democratic party" denote one party; the acronym
    repeats the name, so the label without it is the better canonical form.
    """
    tokens = item.core_tokens
    noise = 0
    for index, token in enumerate(tokens):
        rest = tokens[:index] + tokens[index + 1 :]
        if len(rest) < 2 or len(token) < 2 or len(token) > len(rest):
            continue
        initials = "".join(part[0] for part in rest)
        if sorted(token) == sorted(initials):
            noise += 1
    return noise


def _choose_canonical(members: list[Normalized], counts: dict[str, int]) -> Normalized:
    """The most specific spelling, then the more frequent one, then A→Z.

    Specificity first is deliberate: a cluster of *Orpo*, *PM Orpo* and *Petteri Orpo* must be
    labelled with the full name even when the bare surname is the most common spelling in the
    corpus — the canonical label is what a reader sees, and the surname is the lossy form.
    Organisations are unaffected: legal suffixes are stripped before this comparison, so
    *Fortum Oyj* and *Fortum* carry the same core length and frequency decides.
    """
    # A spelling that carries its own alias in brackets never names a cluster: drop those before
    # specificity is weighed, or "psoe (spanish socialist workers' party)" beats the plain forms.
    plain = [item for item in members if "(" not in item.raw]
    if plain:
        members = plain

    multi_token = [item for item in members if len(item.core_tokens) > 1]
    single_token = [item for item in members if len(item.core_tokens) <= 1]
    # A full name beats a bare surname that was folded into it; among equals, frequency decides,
    # because that is the spelling the corpus (and therefore the reader) actually uses.
    pool = multi_token if (multi_token and single_token) else members
    # Acronym-free first ("social democratic party" beats "spd social democratic party"), then a
    # spelling that does not carry its own aliases in brackets: a canonical label that reads
    # "psoe (spanish socialist workers' party)" is showing its work instead of naming the thing.
    return max(
        pool,
        key=lambda item: (
            0 if "(" not in item.raw else 1,
            -_acronym_noise(item),
            counts.get(item.raw, 0),
            len(item.core_tokens),
            item.raw.casefold(),
        ),
    )


def _surname_targets(entries: list[Normalized]) -> dict[str, set[str]]:
    """For each one-token core, the multi-token cores that contain it.

    ``{"orpo": {"petteri orpo"}}`` means a bare *Orpo* can be resolved. Two entries mean the
    corpus has two Orpos and the bare surname is genuinely ambiguous.
    """
    targets: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        if len(entry.core_tokens) > 1:
            for token in entry.core_tokens:
                targets[token].add(entry.core)
    return targets


def _surname_pair_ok(
    canonical: Normalized,
    member: Normalized,
    rule: CategoryRule,
    surname_targets: dict[str, set[str]],
) -> bool:
    """May a bare surname join this full name, given what else the corpus contains?"""
    if not rule.surname_merge or len(canonical.core_tokens) == len(member.core_tokens):
        return False
    shorter, longer = (
        (canonical, member)
        if len(canonical.core_tokens) < len(member.core_tokens)
        else (member, canonical)
    )
    if len(shorter.core_tokens) != 1:
        return False
    if not set(shorter.core_tokens) < set(longer.core_tokens):
        return False
    # Exactly one full name in the corpus answers to this token: context confirms the person.
    return len(surname_targets.get(shorter.core, set())) == 1


class UnionFind:
    """Small union-find with deterministic merge order, so a re-run is byte-identical."""

    def __init__(self, items: list[str]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != root:
            self.parent[item], item = root, self.parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            first, second = sorted((left_root, right_root))
            self.parent[second] = first

    def groups(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for item in self.parent:
            grouped[self.find(item)].append(item)
        return grouped


def resolve(
    stats: list[LabelStat],
    rule: CategoryRule,
    *,
    forced: list[tuple[str, list[str]]] | None = None,
    blocked: set[frozenset[str]] | None = None,
    forced_methods: dict[str, str] | None = None,
) -> MergeResult:
    """Cluster one category's labels, applying researcher decisions first.

    ``forced`` is a list of ``(canonical, members)`` from the decision log or a human workbook;
    ``blocked`` holds label pairs a researcher explicitly kept apart. Both survive re-runs, which
    is what makes the run resumable without losing manual work.

    Two precedence rules are enforced here rather than left to the caller:

    * a human decision is applied **before** any similarity rule runs, so a matcher can never
      re-derive — or contradict — a pair a researcher already settled;
    * a human-decided label set is **sealed**: an unverified label may not be absorbed into it on
      a similarity score alone. Only a spelling difference that is the same string (case, word
      order, punctuation) may join, and anything else becomes a review candidate. This is what
      stops an automatic union from attaching an unverified alias to a workbook cluster.
    """
    forced = forced or []
    blocked = blocked or set()
    forced_methods = forced_methods or {}
    if not stats:
        return MergeResult()

    def normalize_stat(stat: LabelStat) -> Normalized:
        entry = rule.normalize(stat.label)
        if rule.name != "entity":
            return entry
        alias = party_alias(entry.folded, stat.countries)
        if alias != entry.folded:
            return replace(rule.normalize(alias), raw=entry.raw)
        return entry

    normalized = {stat.label: normalize_stat(stat) for stat in stats}

    def canonical_name(entry: Normalized) -> str:
        if rule.name == "entity" and entry.folded in PARTY_DISPLAY:
            return PARTY_DISPLAY[entry.folded]
        return clean_label(entry.raw) if rule.strip_parentheticals else strip_leading_article(entry.raw)
    counts = {stat.label: stat.count for stat in stats}
    entries = sorted(normalized.values(), key=lambda item: item.raw.casefold())
    surname_targets = _surname_targets(entries) if rule.surname_merge else {}

    #: Corpus spellings by folded form: a workbook writes "Javier Milei", the corpus writes
    #: "javier milei", and both are the same label for the purpose of applying a decision.
    fold_index: dict[str, list[str]] = defaultdict(list)
    for label in normalized:
        fold_index[" ".join(label.split()).casefold()].append(label)

    def spellings(name: str) -> list[str]:
        return sorted(fold_index.get(" ".join(name.split()).casefold(), []))

    uf = UnionFind([entry.raw for entry in entries])
    merged_pairs: set[frozenset[str]] = set()
    #: Pairs a researcher put together. The transitivity guard must not take them apart again:
    #: a decision is not a similarity score.
    forced_pairs: set[frozenset[str]] = set()
    #: Member -> the name the researcher chose for its cluster.
    forced_canonical: dict[str, str] = {}
    #: Member -> which forced group it belongs to, so a group can be sealed as a unit.
    sealed_group: dict[str, int] = {}
    #: Member -> how the decision that fixed it should be named in the run's provenance.
    forced_method_by_label: dict[str, str] = {}

    # Decisions first. Everything below this block is the matcher's opinion, and it may not
    # overrule what the block already decided.
    for number, (canonical, members) in enumerate(forced):
        present = sorted({label for name in {canonical, *members} for label in spellings(name)})
        if not present:
            continue
        method = forced_methods.get(canonical, "forced")
        for label in present:
            forced_canonical[label] = canonical
            sealed_group.setdefault(label, number)
            forced_method_by_label[label] = method
        for left, right in combinations(present, 2):
            forced_pairs.add(frozenset((left, right)))
            uf.union(left, right)
            merged_pairs.add(frozenset((left, right)))

    # Blocking: index every label under each of its tokens, so "orpo" meets "petteri orpo"
    # without comparing the whole corpus pairwise.
    buckets: dict[str, list[str]] = defaultdict(list)
    for entry in entries:
        for token in set(entry.core_tokens):
            buckets[token].append(entry.raw)
    # A token carried by hundreds of labels ("the", "party") is not a blocking key: it would make
    # the block quadratic. Such labels still meet through any other token they share.
    buckets = {token: labels for token, labels in buckets.items() if len(labels) <= MAX_BUCKET}

    scored: dict[frozenset[str], tuple[float, str]] = {}
    #: Pairs the sealing rule held back, with the sentence a reviewer will read.
    sealed_holds: dict[frozenset[str], str] = {}

    def score_pair(left: str, right: str) -> tuple[float, str]:
        pair = frozenset((left, right))
        if pair not in scored:
            scored[pair] = similarity(normalized[left], normalized[right], rule)
        return scored[pair]

    for members in buckets.values():
        for left, right in combinations(sorted(set(members)), 2):
            pair = frozenset((left, right))
            if pair in merged_pairs or pair in blocked:
                continue
            left_entry, right_entry = normalized[left], normalized[right]
            score, relation = score_pair(left, right)
            if score < rule.auto_merge:
                continue
            left_group, right_group = sealed_group.get(left), sealed_group.get(right)
            if left_group is not None or right_group is not None:
                # A human-decided set only grows by another human decision. The one exception is
                # a pure spelling difference (same tokens, possibly another case or order), which
                # is the same string rather than a new judgement — except across two different
                # human clusters, where it would silently overrule both.
                same_string = relation == "token-set"
                if left_group != right_group and not (
                    same_string and (left_group is None or right_group is None)
                ):
                    if score >= rule.review:
                        sealed_holds[pair] = (
                            "human-verified label set: an unverified label may not join on"
                            " similarity alone"
                        )
                    continue
            if relation == "surname" and not _surname_pair_ok(
                left_entry, right_entry, rule, surname_targets
            ):
                continue
            uf.union(left, right)
            merged_pairs.add(pair)

    # Forced clusters were unioned before the matcher ran; re-asserting them here would let a
    # later edit reintroduce the old ordering, so the absence of a second pass is deliberate.

    clusters: list[Cluster] = []
    singletons: list[str] = []

    for _, members in sorted(uf.groups().items(), key=lambda item: item[0].casefold()):
        member_entries = [normalized[member] for member in members]
        if len(member_entries) == 1:
            entry = member_entries[0]
            name = forced_canonical.get(entry.raw, canonical_name(entry))
            if name != entry.raw and not any(entry.raw in pair for pair in blocked):
                clusters.append(
                    Cluster(
                        name,
                        (entry.raw,),
                        1.0,
                        forced_method_by_label.get(entry.raw, "normalization"),
                        counts[entry.raw],
                    )
                )
            else:
                singletons.append(entry.raw)
            continue
        canonical_entry = _choose_canonical(member_entries, counts)
        # A researcher who merged these labels also said what to call the result. Their name
        # wins over the frequency/specificity rule, which is what "canonical" means here.
        decided = next((forced_canonical[item] for item in members if item in forced_canonical), "")
        if decided and decided in normalized:
            canonical_entry = normalized[decided]
        kept = [canonical_entry]
        dropped: list[str] = []
        scores = [1.0]
        methods: set[str] = set()
        # Transitivity guard: a member joins only if it is close to the chosen canonical, not
        # merely close to some other member. A~B and B~C must not drag A and C together.
        for entry in member_entries:
            if entry is canonical_entry:
                continue
            score, relation = similarity(canonical_entry, entry, rule)
            forced_here = frozenset((canonical_entry.raw, entry.raw)) in forced_pairs
            if forced_here:
                methods.add(forced_method_by_label.get(entry.raw, "forced"))
            if forced_here or score >= rule.auto_merge or _surname_pair_ok(
                canonical_entry, entry, rule, surname_targets
            ):
                kept.append(entry)
                scores.append(score)
                methods.add(relation)
            else:
                dropped.append(entry.raw)
        if len(kept) == 1:
            singletons.extend([canonical_entry.raw, *dropped])
            continue
        member_names = sorted(entry.raw for entry in kept)
        clusters.append(
            Cluster(
                canonical=decided or canonical_name(canonical_entry),
                members=tuple(member_names),
                confidence=min(scores),
                method="+".join(sorted(methods)) or "canonical",
                count=sum(counts.get(name, 0) for name in member_names),
            )
        )
        singletons.extend(dropped)

    # One row per label, not one per pair: a researcher judges a label, and a queue of 20 000
    # pairs is not a queue. Alternatives are ranked, and only the closest few are kept.
    alternatives: dict[str, list[tuple[str, float]]] = defaultdict(list)
    reasons: dict[str, str] = {}

    def note(label: str, other: str, score: float, reason: str) -> None:
        alternatives[label].append((other, score))
        reasons.setdefault(label, reason)

    # The same blocking as above: only labels that share a token can be confused, so the
    # candidate list stays linear in the corpus rather than quadratic.
    candidate_pairs: set[frozenset[str]] = set()
    for members in buckets.values():
        for left, right in combinations(sorted(set(members)), 2):
            candidate_pairs.add(frozenset((left, right)))

    for pair in sorted(candidate_pairs, key=lambda item: sorted(item)):
        left, right = sorted(pair)
        if pair in merged_pairs:
            continue
        left_entry, right_entry = normalized[left], normalized[right]
        score, relation = score_pair(left, right)
        if pair in sealed_holds and score >= rule.review:
            # A human decision covers one of these labels; the pair is a question for a person,
            # not for a threshold, so it is queued even when the score is very high.
            note(left, right, score, sealed_holds[pair])
            continue
        if pair in blocked:
            note(left, right, 0.0, "kept apart by a researcher decision")
            continue
        if relation == "surname" and not _surname_pair_ok(
            left_entry, right_entry, rule, surname_targets
        ):
            # "Orpo" would merge on score alone; context says there is more than one Orpo.
            token = left_entry.core if len(left_entry.core_tokens) == 1 else right_entry.core
            targets = sorted(surname_targets.get(token, set()))
            note(
                left,
                right,
                score,
                f"bare surname {token!r} matches {len(targets)} full names: " + ", ".join(targets),
            )
            continue
        if rule.review <= score < rule.auto_merge:
            note(
                left,
                right,
                score,
                f"score {score:.3f} is below the {rule.auto_merge:.2f} auto-merge threshold",
            )

    candidates = [
        ReviewCandidate(
            label=label,
            alternatives=tuple(sorted(options, key=lambda item: (-item[1], item[0]))[:MAX_ALTERNATIVES]),
            reason=reasons[label],
            count=counts.get(label, 0),
        )
        for label, options in sorted(alternatives.items())
        if options
    ]
    candidates.sort(key=lambda candidate: (-candidate.alternatives[0][1], candidate.label))
    return MergeResult(clusters=clusters, candidates=candidates, singletons=sorted(singletons))
