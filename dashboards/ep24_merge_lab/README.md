# Legacy EP24 merge lab (#300)

Automatic deduplication of the labels the legacy EP24 corpus uses — people, entities, themes,
topics and sentiment targets — so a researcher reviews only the cases a rule cannot settle.

This is a **curation tool**, not an analysis tool. It does not read records, infer labels or
reinterpret anything the legacy pipeline produced: it counts the spellings that are already
there, proposes merges, and refuses to decide the ones that need a person.

The second deliverable is `ui/`: a Streamlit page with a real drag-and-drop review surface. It
reads the same run the CLI writes and appends to the same `decisions.jsonl`, so a decision made by
dragging and a decision made with `merge_labels.py decide` are the same act.

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

# freeze the curated mapping into a version, then (separately) point adapters at it
python dashboards/ep24_merge_lab/merge_labels.py export   --out <curation> --reviewer tomi
python dashboards/ep24_merge_lab/merge_labels.py status   --out <curation>
python dashboards/ep24_merge_lab/merge_labels.py activate --out <curation> --export <export id>
python dashboards/ep24_merge_lab/merge_labels.py rollback --out <curation>
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

## Hosting the review surface

The page must never be public: it shows private labels. Bind it to the host's private/tailnet
address and give it the curation root through the environment — it refuses to guess one.

```bash
export LACLAUGPT_EP24_CURATION=<private>/analysis/ep24_legacy_curation
.venv/bin/streamlit run dashboards/ep24_merge_lab/ui/app.py \
    --server.address <private-address> --server.port 8504 --server.headless true
```

`deploy/laclaugpt-ep24-merge-lab.service.example` is the unit template. On Laskin it runs as
`laclaugpt-ep24-merge-lab.service` on `:8504`, next to the AI26 dashboard on `:8501` and the two
legacy EP24 services on `:8502` and `:8503`.

What the page does and does not do:

- it reads the **latest run** (`LATEST`) and nothing else — regenerate with the CLI to review a
  new merge pass;
- every action is validated in Python before it touches a file, and written to the session under
  `<curation>/sessions/<id>.json` on the spot, so a closed tab loses nothing;
- **Commit decisions** appends to `decisions.jsonl`; committing twice writes nothing twice;
- if the session file changed elsewhere, the page refuses to save over it rather than pick a
  winner;
- it never writes to a legacy EP24 dashboard. Export and activation remain stage 3 and opt-in.

A session is a review *of one run*: the page remembers which run it was opened against, and the
CLI must be re-run before a new review round makes sense.

## Export, activation and rollback (stage 3)

Three separate acts, on purpose:

1. **curate** — decisions land in `decisions.jsonl`.
2. **export** — `exports/<export id>/` is an immutable snapshot: `curated_<category>.csv`,
   `alias_map.json`, `counts_preview.csv` and a `manifest.json` naming the base run, its input
   hashes, the decision digest and count, the reviewed/open candidate counts, a per-file sha256
   map and a `mapping_version` derived from it.
3. **activate** — `activation.json` is a pointer to one export id plus its `mapping_version`. It
   changes no dashboard by itself; an adapter that reads it starts serving canonical labels, and
   removing the pointer makes it serve the untouched legacy labels again. `activation_history.jsonl`
   records every activation and rollback.

Properties that are checked, not assumed:

- **occurrences are conserved** — collapsing aliases moves members between clusters, it never
  copies a count; `counts_preview.csv` says `conserved yes` per category, and a mismatch is a bug;
- **an edited export is not served** — the manifest's `mapping_version` is recomputed from the
  files before use, so a hand-edited or half-restored export resolves to *nothing*;
- **sources are never written** — the adapter opens legacy tables read-only, and
  `write_canonicalised` writes a new file named `<source>.canonical-<export id>.csv` beside the
  original with a `.provenance.json`; it refuses a target that equals the source;
- **no double counting** — two spellings of one label inside a single record collapse to one
  occurrence, which is the case alias merging would otherwise inflate.

### Using the mapping from a reader

```python
from ep24_merge_lab import adapters, export

active = export.resolve_active_export(curation_root)      # None when nothing is activated
if active:
    export_dir, manifest = active
    mapping = adapters.load_mapping(export_dir)
    for row in adapters.iter_canonicalised(source_csv, columns={"person": "entities"}, mapping=mapping):
        ...
```

`adapters.count_preview(...)` reports what activation would change — labels before and after,
distinct labels before and after, and how many occurrences collapse — without writing anything.

### Researcher workflow

1. `run` the CLI to produce a new merge pass; `inventory` first if the sources changed.
2. Open the review page, work through the categories, and **Commit decisions**.
3. Re-`run` the CLI: decisions are applied before clustering, so the new tables reflect them.
4. `export`; look at `counts_preview.csv` and `manifest.json`.
5. `activate` when — and only when — the numbers are right. Roll back with one command.
6. The legacy dashboards keep serving untouched files throughout; a dashboard reads canonical
   labels only if it is pointed at the adapter and something is activated.
