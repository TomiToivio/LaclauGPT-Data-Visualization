# Legacy EP24 merge lab (#300)

Automatic deduplication of the labels the legacy EP24 corpus uses — people, entities, themes,
topics and sentiment targets — so a researcher reviews only the cases a rule cannot settle.

This is a **curation tool**, not an analysis tool. It does not read records, infer labels or
reinterpret anything the legacy pipeline produced: it counts the spellings that are already
there, proposes merges, and refuses to decide the ones that need a person.

The interactive Merge Lab (drag-and-drop review) is the second deliverable of #300 and is not
part of this directory yet; the decisions log it will write is already the input this tool reads.

## Where the data lives

Everything — profile, inputs, curated output, decisions — stays in the private repository
(`LaclauGPT-Private`). Nothing in this directory names a private path, and the public tree never
learns one: the profile is passed with `--profile` and the output with `--out`.

```yaml
# <private>/analysis/ep24_legacy_curation/profile.yaml
version: 1
sources:
  - name: legacy-dashboard          # a per-record table: label lists per row
    kind: records
    path: analysis/ep24/backups/<legacy dataframe>.csv
    country_column: country
    lists:
      entities: {column: entities, separator: ","}
      themes: {column: political_themes, separator: "\n"}
      topics: {column: topics, separator: ","}
      sentiment:
        positive: {column: positive, separator: ","}
        negative: {column: negative, separator: ","}
  - name: codebook-entities         # a curated label table: label, aliases, entity_type
    kind: entity_codebook
    path: analysis/ep24/<export>/finland_entities.csv
    country_column: country
    person_types: [person]
  - name: codebook-topics
    kind: topic_codebook
    path: analysis/ep24/<export>/finland_themes.csv
```

`kind: records` contributes the counts the dashboards showed. `kind: entity_codebook` is what
separates **Persons** from other **Entities** — the record columns do not type their mentions, so
a person name found in a record column is moved into the person category when the codebook says
it is a person, and its occurrences follow it (`sources._move_person_labels`).

## Commands

```bash
# what is there, before anything is merged
python dashboards/ep24_merge_lab/merge_labels.py inventory --profile <profile.yaml> --root <private>

# propose merges; --dry-run writes nothing
python dashboards/ep24_merge_lab/merge_labels.py run --profile <profile.yaml> --root <private> \
    --out <private>/analysis/ep24_legacy_curation --dry-run

# write a versioned run
python dashboards/ep24_merge_lab/merge_labels.py run --profile <profile.yaml> --root <private> \
    --out <private>/analysis/ep24_legacy_curation

# record a researcher decision; every later run honours it
python dashboards/ep24_merge_lab/merge_labels.py decide --out <private>/analysis/ep24_legacy_curation \
    --category person --action merge --canonical "Petteri Orpo" --member "Orpo" --reviewer tomi
```

Options worth knowing: `--category` restricts a run to one category; `--min-auto` and `--review`
move the two thresholds for an experiment (a run records the thresholds it used, so two runs are
never silently incomparable).

## What a run leaves behind

```
<out>/decisions.jsonl                     append-only researcher log (read by every run)
<out>/LATEST                              name of the newest run
<out>/runs/<UTC timestamp>/canonical_<category>.csv   canonical label, members, occurrences, confidence
<out>/runs/<UTC timestamp>/review_<category>.csv      pairs the script will not decide
<out>/runs/<UTC timestamp>/alias_map.csv              every alias -> canonical, with its method
<out>/runs/<UTC timestamp>/stats.json                 counts per category
<out>/runs/<UTC timestamp>/manifest.json              input sha256s, thresholds, output sha256s
```

Runs are never overwritten or mutated: an earlier curated version can be re-read, compared or
rolled back to. `manifest.json` is what makes that checkable rather than a promise.

## The rules, per category

| category | normalization | may merge on | never merges |
| --- | --- | --- | --- |
| `person` | case, unicode, punctuation, leading titles (`PM`, `Prime Minister`) | same token set; or one word inside a full name when exactly **one** full name answers to it | a bare surname that matches two people |
| `entity` | case, unicode, punctuation, legal suffixes (`Oy`, `Oyj`, `AB`, `GmbH`…) | same token set, containment, or ≥0.92 | across categories (a person is not an organisation) |
| `theme` | case, unicode, punctuation | token-set near-equality ≥0.90 | containment: sharing *Europe* is not being the same theme |
| `topic` | as theme | as theme | as theme, and near-misses are candidates only |
| `sentiment` | as theme | same phrase **inside one polarity** | across polarity — the same phrase can be praised and condemned |

Three properties are deliberate:

- **No unsafe transitive merges.** A member joins a cluster only if it is similar to the chosen
  canonical, not merely similar to some other member: `A~B` and `B~C` never drag `A` and `C`
  together.
- **The canonical spelling is the most specific one.** A cluster of *Orpo*, *PM Orpo* and
  *Petteri Orpo* is labelled `Petteri Orpo` even when the bare surname is more frequent, because
  the canonical label is what a reader sees; the surname is the lossy form.
- **A researcher outranks the matcher.** `merge` and `keep_separate` decisions are applied before
  clustering and are exempt from the similarity guard, so re-running never undoes manual work.

## Tests

`tests/test_ep24_merge_lab.py` — synthetic only, including #300's Orpo example, a surname that
matches two people, a multilingual spelling pair, themes that share a word, opposing sentiment
polarities, the transitivity guard, and a decision surviving a second run.
