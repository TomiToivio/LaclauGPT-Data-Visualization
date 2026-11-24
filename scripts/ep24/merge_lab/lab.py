"""Offline curation of the original EP24 dashboard CSV contract."""
import argparse
import csv
import hashlib
import io
import itertools
import json
import re
import sqlite3
import unicodedata
import zlib
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

FIELDS = {"entities": ("Entities", ", "), "new_theme": ("Themes", ";"),
          "new_entity": ("Persons", ";"), "topics": ("Topics", ", "),
          **{key: ("Sentiments", ", ") for key in ("positive", "neutral", "negative")}}
CATEGORIES = tuple(dict.fromkeys(group for group, delim in FIELDS.values()))


def norm(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def oid(field, label, source):
    # Short identity mentions require observation-specific disambiguation.
    identity = field in ("entities", "new_entity")
    return digest([field, label, source if identity else None])


def source_id(row, path, *, record_number=None, snapshot=None):
    if row.get("source_url"):
        return row["source_url"]
    country = row.get("country") or path.stem
    if not (row.get("new_id") or row.get("video_id")):
        if record_number is None or not snapshot:
            raise ValueError("Unidentified record needs a pinned snapshot and record number")
        return json.dumps(["legacy-row", path.name, snapshot, record_number])
    return json.dumps([country, row.get("new_id") or row["video_id"]])


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        sample = stream.readline()
        stream.seek(0)
        # A header has no escaped quotes. Sniff only its delimiter so that quoted
        # transcripts with doubled quotes and embedded newlines remain one record.
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t").delimiter
        csv.field_size_limit(max(csv.field_size_limit(), 10**9))
        reader = csv.DictReader(stream, delimiter=delimiter)
        if set(FIELDS) - set(reader.fieldnames or ()):
            raise ValueError(f"Missing legacy columns in {path.name}. Check Git LFS checkout.")
        yield from reader


def inventory(paths, threshold=0.88, equivalents=None):
    aliases, inputs = {}, {}
    hasher = hashlib.file_digest if hasattr(hashlib, "file_digest") else None
    for path in sorted(paths):
        with path.open("rb") as stream:
            inputs[path.name] = (hasher(stream, "sha256") if hasher else
                                 hashlib.sha256(stream.read())).hexdigest()
        for number, row in enumerate(read_rows(path), start=1):
            source = source_id(row, path, record_number=number, snapshot=inputs[path.name])
            context = row.get("summary_analysis") or ""
            for field, (_, delimiter) in FIELDS.items():
                for label in (item.strip() for item in row[field].split(delimiter)):
                    if norm(label) in ("", "none", "nan"):
                        continue
                    key = oid(field, label, source)
                    alias = aliases.setdefault(key, {"field": field, "label": label, "refs": {}})
                    alias["refs"][source] = [row.get("country", ""), row.get("whisper_language", ""), context]
    families = defaultdict(set)
    for alias in aliases.values():
        label = norm(alias["label"])
        if alias["field"] in ("entities", "new_entity") and len(label.split()) == 2 and not re.match(
                r"^(?:pm|minister|president|pääministeri) ", label):
            families[alias["field"], label.split()[-1]].add(label)
    groups, spellings, candidates = {}, defaultdict(set), set()
    for key, alias in sorted(aliases.items()):
        field, label = alias["field"], alias["label"]
        normal = norm(label)
        target = (equivalents or {}).get(field, {}).get(normal, normal)
        reason = "approved equivalence" if target != normal else "normalized spelling"
        possible = set()
        if field in ("entities", "new_entity"):
            short = re.sub(r"^(?:prime minister|pm|pääministeri) ", "", normal)
            if len(short.split()) == 1:
                possible = families[field, short]
                context = norm(next(iter(alias["refs"].values()))[2])
                matches = [name for name in possible if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", context)]
                if len(matches) == 1:
                    target, reason = matches[0], "full name in observation"
                elif possible or (field == "new_entity" and target == normal):
                    target, reason = key, "ambiguous identity"
        group = digest([field, norm(target)])
        alias.update(initial=group, reason=reason, confidence={"normalized spelling": 1.0,
                     "approved equivalence": 1.0, "full name in observation": .95,
                     "ambiguous identity": 0.0}[reason])
        spellings[group].add(target if reason in ("approved equivalence", "full name in observation") else label)
        groups.setdefault(group, []).append(key)
        if reason == "ambiguous identity":
            candidates.update(tuple(sorted((group, digest([field, name])))) for name in possible)
    names = {g: min(options, key=lambda x: (x.islower(), x)) for g, options in spellings.items()}
    blocks = defaultdict(list)
    for group, name in names.items():
        blocks[aliases[groups[group][0]]["field"], norm(name)[:2]].append(group)
    for block in blocks.values():
        for a, b in itertools.combinations(block, 2):
            if SequenceMatcher(None, norm(names[a]), norm(names[b])).ratio() >= threshold:
                candidates.add(tuple(sorted((a, b))))
    return {"inputs": inputs, "aliases": aliases, "candidates": sorted(candidates),
                "groups": groups, "names": names, "separate": [], "reviewed": 0}


def transition(state, action, ids, label="", member=None):
    groups, names = state["groups"], state["names"]
    if not ids or len(set(ids)) != len(ids) or any(g not in groups for g in ids):
        raise ValueError("Select current clusters")
    fields = {state["aliases"][k]["field"] for g in ids for k in groups[g]}
    if len(fields) != 1:
        raise ValueError("Select clusters in the same category and polarity")
    field = next(iter(fields))
    if action in ("merge", "rename", "split") and (
            not label.strip() or FIELDS[field][1] in label or norm(label) in ("none", "nan")):
        raise ValueError("Choose a nonempty label compatible with the legacy separator")
    if action in ("merge", "separate") and len(ids) < 2:
        raise ValueError("Select at least two clusters")
    if action in ("rename", "split") and len(ids) != 1:
        raise ValueError("Select one cluster")
    first = ids[0]
    if action == "separate":
        for a, b in itertools.combinations(ids, 2):
            state["separate"].append([groups[a][:], groups[b][:]])
    elif action == "merge":
        selected = set(itertools.chain.from_iterable(groups[g] for g in ids))
        if any(selected.intersection(a) and selected.intersection(b) for a, b in state["separate"]):
            raise ValueError("A keep-separate decision protects these observations")
        for other in ids[1:]:
            groups[first].extend(groups.pop(other))
            del names[other]
        names[first] = label.strip()
    elif action == "rename":
        names[first] = label.strip()
    elif action == "split":
        if member not in groups[first] or len(groups[first]) < 2:
            raise ValueError("Select a member of a multi-member cluster")
        new = digest([first, member, state["reviewed"]])
        groups[first].remove(member)
        groups[new], names[new] = [member], label.strip()
    else:
        raise ValueError("Unknown decision")
    state["reviewed"] += 1


def connect(root):
    root = Path(root).resolve()
    if not (root / ".git").exists() or not (root / "analysis/ep24/source").is_dir():
        raise ValueError("Expected a private study checkout")
    area = root / "analysis/ep24_legacy_curation"
    area.mkdir(exist_ok=True)
    db = sqlite3.connect(area / "session.sqlite", isolation_level=None)
    db.execute("CREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY,parent INTEGER,state TEXT,action TEXT)")
    db.execute("CREATE TABLE IF NOT EXISTS head(slot INTEGER PRIMARY KEY,revision INTEGER,version INTEGER,redo TEXT)")
    return db, area


def current(db):
    row = db.execute("SELECT revision,state FROM head JOIN versions ON versions.id=head.version").fetchone()
    if row is None:
        raise ValueError("Initialize the inventory first")
    return row[0], json.loads(zlib.decompress(row[1]))


def save(db, expected, action, args=(), initial=None):
    db.execute("BEGIN IMMEDIATE")
    try:
        head = db.execute("SELECT revision,version,redo FROM head").fetchone()
        if (head[0] if head else 0) != expected:
            raise ValueError("Session changed. Reload before applying this decision.")
        parent = head[1] if head else None
        redo = json.loads(head[2]) if head else []
        if action == "undo":
            version = db.execute("SELECT parent FROM versions WHERE id=?", (parent,)).fetchone()[0]
            if version is None:
                raise ValueError("At first version")
            redo.append(parent)
        elif action == "redo":
            if not redo:
                raise ValueError("No decision to redo")
            version = redo.pop()
        else:
            state = initial
            if head:
                state = current(db)[1]
                transition(state, action, *args)
            version = db.execute("INSERT INTO versions(parent,state,action) VALUES (?,?,?)",
                                 (parent, zlib.compress(json.dumps(state).encode()), json.dumps([action, args]))).lastrowid
            redo = []
        db.execute("INSERT OR REPLACE INTO head VALUES(1,?,?,?)", (expected+1, version, json.dumps(redo)))
        db.commit()
    except BaseException:
        db.rollback()
        raise


def curated_rows(path, state):
    with path.open("rb") as stream:
        if hashlib.sha256(stream.read()).hexdigest() != state["inputs"].get(path.name):
            raise ValueError("Source snapshot checksum mismatch")
    mapping = {k: state["names"][g] for g, keys in state["groups"].items() for k in keys}
    for number, row in enumerate(read_rows(path), start=1):
        source = source_id(row, path, record_number=number, snapshot=state["inputs"][path.name])
        for field, (_, sep) in FIELDS.items():
            labels = [x.strip() for x in row[field].split(sep)]
            resolved = [mapping.get(oid(field, x, source), x) for x in labels]
            row[field] = sep.join(dict.fromkeys(resolved))
        yield row


def csv_bytes(rows):
    out = io.StringIO(newline="")
    writer = None
    for row in rows:
        if writer is None:
            writer = csv.DictWriter(out, fieldnames=row.keys())
            writer.writeheader()
        writer.writerow(row)
    return out.getvalue().encode()


def validate_export(directory):
    """Validate a pinned export before handing its CSV paths to a legacy reader."""
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["schema"] != "legacy-ep24-dashboard-csv-v1" or manifest["review_status"] != "researcher-approved":
        raise ValueError("Expected an approved legacy export")
    result = []
    for name, checksum in manifest["export_sha256"].items():
        if Path(name).name != name or not name.endswith(".csv"):
            raise ValueError("Unexpected dashboard table path")
        path = directory / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise ValueError("Export checksum mismatch")
        if sum(1 for _ in read_rows(path)) != manifest["record_counts"][name]:
            raise ValueError("Export row count mismatch")
        result.append(path)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("private_checkout", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--threshold", type=float, default=.88)
    parser.add_argument("--equivalences", type=Path, help="Reviewed JSON: field -> normalized alias -> canonical")
    args = parser.parse_args()
    paths = sorted((args.private_checkout / "analysis/ep24/source").glob("*_dashboard_*.csv"))
    if not paths or not 0 <= args.threshold <= 1:
        parser.error("Expected legacy dashboard CSVs and a threshold between zero and one")
    seed = inventory(paths, args.threshold, json.loads(args.equivalences.read_text()) if args.equivalences else None)
    print(f"{len(seed['aliases'])} alias entries, {len(seed['groups'])} clusters, {len(seed['candidates'])} candidates")
    if not args.dry_run:
        db, area = connect(args.private_checkout)
        if db.execute("SELECT 1 FROM head").fetchone():
            if current(db)[1]["inputs"] != seed["inputs"]:
                raise ValueError("Source snapshot changed. Preserve the prior session before starting another.")
        else:
            save(db, 0, "inventory", initial=seed)
