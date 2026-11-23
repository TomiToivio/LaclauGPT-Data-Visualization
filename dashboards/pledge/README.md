# PLEDGE grievance dashboard

The researcher-facing stream of the PLEDGE / EP2024 grievance corpus: filters, grievance list,
sentiment, and the per-topic / entity / theme rankings.

## Where it runs

It is deployed **from its data directory**, not from this repository:

```
<presentation-host>:<data-root>/laclaugpt/pledge_dashboard/
    pledge_dashboard.py      this directory's file, unchanged
    pledge_search.py         ├─ copied alongside it
    pledge_entities.py       ┘
    ep24_pledge_clean_v2.csv the data (backed up in the private repository: analysis/pledge/)
```

```bash
cd <data-root>/laclaugpt/pledge_dashboard
setsid nohup python3 -m streamlit run pledge_dashboard.py \
  --server.port 8501 --server.headless true --server.address 0.0.0.0 \
  --browser.gatherUsageStats false > <log-dir>/pledge_app.log 2>&1 < /dev/null &
```

Use `setsid` + `nohup`: a plain `&` in an SSH one-liner dies with the session, and the app then
serves nothing (`health=000`).

## What this copy is for

Backup and review. The canonical runnable copy is the one on the presentation host; this directory
keeps the code under version control next to a test that exercises it, so a change can be reviewed
before it is copied over.

## The two rules worth knowing

- **Search** (`pledge_search.py`) covers a chosen scope — universal number (`video_id`), grievances,
  topics, entities, themes, persons — and matches the query **literally**. Search that inspected
  `grievances` alone could never find a universal number, and `str.contains`'s default `regex=True`
  turned a query like `(rent + bills)` into a pattern.
- **Entity merging** (`pledge_entities.py`) splits each comma-joined cell into tags, folds variants
  of one referent (`eu`, `european union eu` → `european union`; `politician` → `politicians`),
  dedupes, and rejoins. Institutions that merely look similar stay apart: `european commission` is
  not the European Union.
