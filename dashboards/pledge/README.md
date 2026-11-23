# PLEDGE grievance dashboard

The researcher-facing stream of the PLEDGE / EP2024 grievance corpus: filters, grievance list,
sentiment, and the per-topic / entity / theme rankings.

## Where it runs

It is deployed **from its data directory**, not from this repository:

It runs from the dashboard's data directory on the presentation host:

```
pledge_dashboard.py      this directory's file, unchanged
pledge_search.py         ├─ copied alongside it
pledge_entities.py       ┘
ep24_pledge_clean_v2.csv the data (archived in LaclauGPT-Private: analysis/pledge/)
```

```bash
cd <dashboard-data-dir>
setsid nohup python3 -m streamlit run pledge_dashboard.py \
  --server.port 8501 --server.headless true --server.address 0.0.0.0 \
  --browser.gatherUsageStats false > pledge_app.log 2>&1 < /dev/null &
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
- **Entity merging** (`pledge_entities.py`) is corpus-driven, not a hand list. Cells are
  comma-joined tags, so each is split, folded through a map *learned from the column*
  (`build_forms`), deduped and rejoined. It folds a leading `the`, accents, punctuation and `/`/`&`,
  a *qualifying* parenthesis (`european union (eu)`), singular/plural and a trailing `party` — each
  only when both forms actually occur. The most frequent spelling wins, so the accented form
  (`pedro sánchez`) beats the flattened one.

### Checking it

```bash
python tools/audit_pledge_labels.py ep24_pledge_clean_v2.csv
```

The audit groups tokens under a deliberately *aggressive* key (accents, case, punctuation and all
parentheses removed) and prints what still holds more than one token. Current state on the
12,394-row workbook:

```
entities: 4521 tokens | groups needing judgement 146 | behind a parenthesis 1.52% of occurrences
topics:   4704 tokens | groups needing judgement  22 | behind a parenthesis 0.14%
persons:   247 tokens | groups needing judgement   0
themes:    125 tokens | groups needing judgement   0
```

A remaining group is not automatically a bug: `government` / `government (france)` are different
governments, and `european commission` is not the European Union. What is left is the class a rule
cannot decide — a parenthesis naming a place, party or person — and it is 1.5% of occurrences.

## Restarting

```bash
bash start_pledge.sh 8501
```

It kills the PID that owns the port and waits for health. Do **not** use
`pkill -f "streamlit run pledge_dashboard.py"` in an SSH one-liner: the pattern matches the
one-liner's own command line, so the shell is killed and the app stays down.

