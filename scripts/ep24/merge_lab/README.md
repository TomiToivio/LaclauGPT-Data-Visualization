# Legacy EP24 Merge Lab

The private repository holds the Finnish and Polish legacy inputs under
`analysis/ep24/source/ep24_{finland,poland}_dashboard_9_1_2026.csv`. Hydrate
them with Git LFS in an authorized private checkout. The source directory also
contains entity/theme workbooks and research notes. Counts here come from the
CSV observations. The original postprocess dashboard's column contract is:

| Category | Field | Within-cell separator |
| --- | --- | --- |
| Entities | entities | comma and space |
| Themes | new_theme | semicolon |
| Persons | new_entity | semicolon |
| Topics | topics | comma and space |
| Sentiments | positive, neutral, negative | comma and space within each polarity |

From the visualization checkout, with Streamlit installed:

```sh
export EP24_PRIVATE_CHECKOUT=/path/to/LaclauGPT-Private
python scripts/ep24/merge_lab/lab.py "$EP24_PRIVATE_CHECKOUT" --dry-run
python scripts/ep24/merge_lab/lab.py "$EP24_PRIVATE_CHECKOUT"
streamlit run scripts/ep24/merge_lab/app.py --server.address=127.0.0.1
```

The CLI conservatively merges normalized spellings, explicitly curated synonyms
and title/surname variants with a matching full name in the observation summary.
Fuzzy similarity only proposes review. Use `--threshold` to change its cutoff
and `--equivalences file.json` for a field-scoped multilingual mapping,
e.g. `{"entities":{"euroopan unioni":"European Union","european union":"European Union"}}`.
Use normalized alias keys. Initialization is idempotent; existing decisions take
precedence on resume. To compare alternative initial settings use a separate
private checkout.

Open a category, inspect a suggested pair, drag cards together or select multiple
clusters with the keyboard. Check the source contexts, choose the name and
confirm the merge or keep the clusters separate. A split moves the selected
alias entry. Confirmed changes autosave in the private checkout's
`analysis/ep24_legacy_curation/session.sqlite`. Undo and redo traverse saved
revisions. Share one server/checkout for concurrency control. For private Git
backup, stop the server and commit the closed database and approved exports
using the private repository's Git LFS rules.

Approval writes a pinned directory under `analysis/ep24_legacy_curation/exports/`
with both compatible dashboard CSVs, the full mapping/lineage and a manifest.
The mapping's refs associate original labels with distinct source observations.
The CSV adapter replaces only label fields and collapses duplicate canonical
labels within each observation and polarity. Use `lab.validate_export(path)`
to obtain verified CSV paths for a researcher-selected revision. Load those
paths only in an explicitly configured legacy dashboard import. Roll back by
selecting the previous revision or original source paths.

Run the synthetic integration test with `python tests/test_ep24_merge_lab_session.py`.

For a separately configured legacy reader, call
`pd.DataFrame.from_records(load_dashboard_rows(private_checkout, revision))`
from `import_version.py`. The adapter requires an explicit revision on each
load. To verify the handoff without opening a dashboard:

```sh
python scripts/ep24/merge_lab/import_version.py "$EP24_PRIVATE_CHECKOUT" --revision 2
```
