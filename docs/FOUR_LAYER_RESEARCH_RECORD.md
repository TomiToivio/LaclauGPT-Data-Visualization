# Four-layer research record in Data Visualization

Visualization is a view over the canonical record. It must not hide the evidence trail researchers used in older EP24 dataframes and dashboards.

## View contract

Visualization reconstructs the nested canonical record before creating a DataFrame. The common view contains:

- raw collected/scraped material or its durable reference;
- intermediate ASR/Whisper, translation, OCR, frames and frame/multimodal analysis;
- all current structured LaclauGPT analysis fields;
- the human-readable researcher summary/report;
- populated legacy dataframe aliases.

The Researcher Review page explicitly shows the human-readable report, Whisper/ASR, OCR, frame analysis, legacy fields, raw capture, intermediate stage outputs and new structured analysis.

The Research Data tab exposes the full researcher dataframe. Familiar fields such as `whisper_transcript`, `whisper_language`, `whisper_translated`, `ocr_1...ocr_6`, `frame_1...frame_6`, `summary_analysis`, source/ID/date fields, Formula-of-Populism aliases and imported historical topic/classifier columns remain visible in addition to new LaclauGPT columns.

Historical EP24 CSV rows are losslessly retained under `legacy` and `raw_capture.payload` while also being adapted into the current view model. MongoDB `_id` is never used as research identity; `source_url` remains canonical.

A backend change must not change this semantic view. Files/CSV/JSONL, SQLite and MongoDB all feed the same canonical reconstruction and flattening path.
