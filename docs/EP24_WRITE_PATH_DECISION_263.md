# Where a researcher's judgement lands (#263 §4)

**This is a decision brief, not a decision.** The dashboard currently records no judgements. Everything below
is implemented, measured, or verified except the choice itself, which belongs to the owner of the corpus.

## What the legacy workbench did

`analysis/ep24/backups/dashboards/ep2024_postprocess-8501/dashboard.py` wrote sixteen fields per video to
MongoDB, `spectacleScraper.ep24_dataframe`, keyed by `new_id`:

| group | fields |
| --- | --- |
| review state | `video_checked`, `dubious_video`, `delete_video`, `wrong_language` |
| rerun requests | `rerun_llm`, `rerun_ocr`, `rerun_whisper` |
| edit requests | `cut_video` + `cut_at` + `cut_keep`, `split_video` + `split_at` |
| correction | `new_persons`, `new_themes`, `researcher_note` |

Two properties of that implementation matter for the decision:

1. **It wrote over itself.** `add_to_mongo` did `update_one({"new_id": ...}, {"$set": notes}, upsert=True)`, so
   the last save wins and there is no record of who judged what, when, or what changed.
2. **Its save path was broken for one field.** `add_to_mongo` takes no `wrong_language` argument but puts
   `wrong_language` in the document, so any save after the flag was added raises `NameError`. The flag exists in
   the schema and cannot have been written by that code path.

The write target is also gone: nothing listens on `27017` on the host that the URI in
`LaclauGPT-Data-Analysis/.env` points at. Whatever review state that collection held is not reachable from the
current deployment, and is not in the export.

## What exists today

Measured over all 1,500 records of `fiplpt_500_20261115`, two of the sixteen fields survive as read-only
residue in the export: `needs_resplit` (368 set, 24.5%) and `researcher_note` (91 non-empty, 6.1%). The other
fourteen are absent — not empty, absent.

So: 368 videos are flagged for a re-split with no reason recorded anywhere this dashboard can reach, and 94% of
the corpus has never been annotated. Neither figure says the corpus is clean; both say how small the reviewed
fraction is.

## The options

### A. Append-only judgement log in the private repository

One file per judgement, or a JSONL append per action, committed to `LaclauGPT-Private` beside the export.

* **Gains:** every judgement has a timestamp and an author; history is the file; a reviewer can diff it; the
  data lives where the corpus already lives and inherits its access control; no new service to operate.
* **Costs:** a dashboard writing to a git repository needs a host key and a commit path, which is a real
  privilege for a web app; concurrent researchers need a merge strategy; LFS does not help (small files, many
  commits); and the repository becomes a runtime dependency of a UI.
* **Answer to "who sees a judgement before review?":** everyone with repository access, immediately and
  permanently.

### B. Redis queue with an export step

Actions are pushed to Redis (already the coordination layer on that host) and a worker folds them into the
export on a schedule.

* **Gains:** fits the stated infrastructure canon (Redis for queues, MongoDB for canonical records); the UI
  never blocks on disk; a worker can deduplicate and validate before anything persists.
* **Costs:** two new moving parts (queue + worker) and a lag between a judgement and its visibility; Redis is
  not durable by default, so a crash between action and fold loses the judgement unless persistence is
  configured; and until the fold runs, "what did I just flag?" has no answer in the UI.
* **Answer to "who sees a judgement before review?":** nobody until the worker folds it, then everyone.

### C. Back to MongoDB (the legacy collection, repaired)

Restore a Mongo instance and write the sixteen fields there again, with an append-only audit collection.

* **Gains:** the schema and the legacy reader already exist; if any of the old review state is ever recovered,
  it lands in the same place; researchers who used `:8501` keep their mental model.
* **Costs:** a database to operate and back up for 16 booleans per video; the legacy schema has no author, no
  timestamp and last-write-wins, so it must be extended before it can be trusted — which means a migration,
  not a restoration; and the deployment would take on a stateful dependency it does not currently have.
* **Answer to "who sees a judgement before review?":** whoever can read the collection — which today is a
  credential held by the host, not a per-researcher identity.

### D. Local-first, per-researcher files (no server writes)

Each researcher's judgements stay in their browser/session download, and merging them into the corpus is a
deliberate act by whoever owns the data.

* **Gains:** no write privilege for the dashboard at all; nothing a visitor does can alter the corpus; the merge
  is reviewed like any other data change.
* **Costs:** no coordination — two researchers flag the same video and neither sees the other; the "reviewed
  fraction" figure becomes per-person rather than per-corpus, so the 24.5% number stops meaning what it says.
* **Answer to "who sees a judgement before review?":** nobody, by construction.

## What each option implies for the numbers on the dashboard

The coverage table added in this increment ("368 of 1,500 flagged, 91 of 1,500 noted") is only meaningful if
judgements accumulate in one place. Option D turns it into a per-researcher figure that must be relabelled;
Options A and C keep it corpus-wide; Option B keeps it corpus-wide with a delay.

## Recommendation, stated as a recommendation

**A**, with an append-only file per action and the merge done by the owner rather than by the app, because it is
the only option where a judgement carries an author and a time without adding a service, and because the
corpus's access control already exists there. It requires the one thing this brief cannot supply: a host key
with commit rights, which is a privilege decision.

If the write privilege is unacceptable, **D** is the honest fallback, and the coverage table must then be
labelled per researcher — not doing so would turn a design constraint into a false claim about the corpus.

## What is blocked on the decision

* the nine legacy per-record actions (`video_checked`, `dubious_video`, three reruns, cut, split, three
  correction fields) — no UI is offered for them, deliberately, rather than a form that discards input;
* any figure that says "N of M reviewed" as a corpus-wide statement;
* the review-related part of parity with `:8501`, which cannot be closed by reading alone.
