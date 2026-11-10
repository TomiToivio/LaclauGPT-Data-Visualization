"""FI/PL/PT live steps 1–7 research explorer.

Launch:
    LACLAUGPT_VIS_LIVE_STEPS_DATA=<artifact dir> \\
        streamlit run src/laclaugpt_visualization/live_steps_app.py

The artifacts come from ``tools/build_live_steps_artifacts.py``. This app reads them only: an index
row per video, a gzipped text bundle for the long cells, and the manifest that says which source
columns were dropped and why. A missing stage renders as *unavailable in this source*, never as 0.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from laclaugpt_visualization.live_steps import (
        STEPS,
        bundle_text,
        child_records,
        clean,
        filter_records,
        load,
        node_degrees,
        sentiment_totals,
        stage_availability,
        status_counts,
        step_table,
        value_counts,
    )
except ModuleNotFoundError:  # standalone deployment: only this module and its helper were shipped
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from live_steps import (  # type: ignore[no-redef]
        STEPS,
        bundle_text,
        child_records,
        clean,
        filter_records,
        load,
        node_degrees,
        sentiment_totals,
        stage_availability,
        status_counts,
        step_table,
        value_counts,
    )

ROOT = (os.environ.get("LACLAUGPT_VIS_LIVE_STEPS_DATA")
        or os.environ.get("LACLAUGPT_VIS_ANALYSIS_DATA_DIR") or "data")

st.set_page_config(page_title="NoöPunk · FI/PL/PT live steps 1–7", layout="wide")

frame, manifest = load(ROOT)
if frame.empty:
    st.title("FI/PL/PT live steps 1–7")
    st.info("No export found at this data root. Point LACLAUGPT_VIS_LIVE_STEPS_DATA at the artifact "
            "directory built by tools/build_live_steps_artifacts.py. No records are fabricated.")
    st.stop()

st.title("FI/PL/PT live pipeline · steps 1–7")
st.caption("Read-only multimodal evidence · Finland, Poland, Portugal · every long value is verbatim "
           "from the producer export")

# -- sidebar: one filter path ------------------------------------------------------------------- #
st.sidebar.markdown("### Corpus")
st.sidebar.caption(f"{len(frame):,} videos in this export "
                   f"({', '.join(f'{k} {v}' for k, v in frame['country'].value_counts().items())})")
countries = st.sidebar.multiselect("Country", sorted(frame["country"].dropna().unique()))
platforms = st.sidebar.multiselect("Platform", sorted(frame["source_type"].dropna().unique()))
political = st.sidebar.multiselect("Political preference",
                                   sorted(frame["political_preference"].dropna().unique()))
months = st.sidebar.multiselect("Recording month", sorted(frame["month"].dropna().unique()))
min_steps = st.sidebar.slider("At least this many of steps 1–7 complete", 0, 7, 0)
query = st.sidebar.text_input("Video ID contains")
st.sidebar.caption("Recording month is derived from the media id (YYYYMMDD), not a producer field.")

filtered = filter_records(frame, countries=countries, platforms=platforms, political=political,
                          months=months, query=query, min_steps=min_steps)
st.caption(f"{len(filtered):,} of {len(frame):,} videos match the filters.")

tabs = st.tabs(["Overview", "Steps & coverage", "Record browser", "Discourse · DNA",
                "Network · SNA", "Aggregates", "Data quality", "Methods"])


def chart(series: pd.Series, title: str, x: str = "records"):
    if series.empty:
        st.info(f"No data for: {title}")
        return
    data = series.rename(x).reset_index()
    data.columns = [c if c != "index" else "value" for c in data.columns]
    st.plotly_chart(px.bar(data, x=x, y=data.columns[0], title=title), use_container_width=True)


def table(rows: list[dict], key: str, caption: str = ""):
    """A dataframe whose selected row opens in the inspector."""
    if not rows:
        st.info("No exported evidence available for this view.")
        return
    display = pd.DataFrame(rows).astype(str).replace({"nan": "", "None": ""})
    if caption:
        st.caption(caption)
    event = st.dataframe(display, use_container_width=True, on_select="rerun",
                         selection_mode="single-row", key=key)
    selection = getattr(event, "selection", None)
    chosen = list(getattr(selection, "rows", []) or [])
    if chosen and "record_id" in display.columns:
        st.session_state["live_inspect"] = display.iloc[chosen[0]]["record_id"]


with tabs[0]:
    columns = st.columns(4)
    columns[0].metric("Videos", f"{len(filtered):,}")
    columns[1].metric("Countries", filtered["country"].nunique() if len(filtered) else 0)
    columns[2].metric("All 7 steps", int((pd.to_numeric(filtered["pipeline_steps_ok"], errors="coerce") == 7).sum()))
    with_sna = filtered["has_sna"].astype(str).str.lower().isin({"true", "1"}) if "has_sna" in filtered else pd.Series(dtype=bool)
    columns[3].metric("With SNA", int(with_sna.sum()))
    left, right = st.columns(2)
    with left:
        chart(filtered["country"].value_counts(), "Videos by country")
        chart(filtered["political_preference"].value_counts(), "Videos by political preference")
        chart(filtered["month"].value_counts().sort_index(), "Videos by recording month")
    with right:
        chart(filtered["source_type"].value_counts(), "Videos by platform")
        chart(filtered["asr_language"].value_counts(), "ASR language")
        chart(pd.to_numeric(filtered["pipeline_steps_ok"], errors="coerce")
              .value_counts().sort_index(), "Steps 1–7 completed")

with tabs[1]:
    st.subheader("Stage coverage")
    st.caption("Denominator is the exported records of that country. A stage the producer did not "
               "report is *unavailable*, not zero.")
    availability = stage_availability(manifest)
    if availability.empty:
        st.info("No stage coverage in the manifest.")
    else:
        st.dataframe(availability, use_container_width=True)
        st.plotly_chart(px.bar(availability, x="stage", y="pct", color="country", barmode="group",
                               title="Per-stage coverage (%)"), use_container_width=True)
    st.subheader("Step status per record")
    steps = step_table(filtered)
    if not steps.empty:
        st.dataframe(steps, use_container_width=True)
        st.plotly_chart(px.bar(steps, x="stage", y="pct", color="country", barmode="group",
                               title="Step completion in the current selection (%)"),
                        use_container_width=True)
    with st.expander("Status vocabulary as the producer wrote it"):
        for step, (label, _, _) in STEPS.items():
            column = f"step_0{step}_status"
            if column in filtered.columns:
                st.markdown(f"**Step {step} · {label}**")
                st.dataframe(status_counts(filtered, column), use_container_width=True)

with tabs[2]:
    st.subheader("Record browser")
    if filtered.empty:
        st.info("No records match the filters.")
    else:
        names = filtered[["record_id", "country", "video_id"]].astype(str)
        labels = [f"{row.country} · {row.video_id}" for row in names.itertuples()]
        wanted = st.session_state.get("live_inspect")
        default = next((i for i, label in enumerate(labels)
                        if wanted and wanted.endswith(clean(names.iloc[i]["video_id"]))), 0)
        picked = st.selectbox("Record", range(len(labels)), index=default,
                              format_func=lambda i: labels[i])
        row = filtered.iloc[picked]
        st.session_state["live_inspect"] = clean(row.get("record_id"))
        st.caption(f"{clean(row.get('record_id'))} · {clean(row.get('source_type'))} · "
                   f"{clean(row.get('political_preference'))} · "
                   f"{clean(row.get('duration_minutes'))} min · {clean(row.get('month'))}")

        long_fields = [field for _, (_, text_fields, _) in STEPS.items() for field in text_fields]
        bundle = bundle_text(ROOT, long_fields).get(clean(row.get("record_id")), {})
        st.markdown("**Producer metadata**")
        st.dataframe(pd.DataFrame([{key: clean(row.get(key)) for key in
                                    ("video_id", "_storage_id", "allas_filename", "source_recording",
                                     "sequence_number", "author_username", "account_type",
                                     "political_preference", "duration_minutes")}]),
                     use_container_width=True)
        for step, (label, text_fields, index_fields) in STEPS.items():
            status = clean(row.get(f"step_0{step}_status")) or "not reported"
            with st.expander(f"Step {step} · {label} · {status}"):
                meta = {key: clean(row.get(key)) for key in index_fields if clean(row.get(key))}
                if meta:
                    st.write(meta)
                shown = False
                for field in text_fields:
                    value = bundle.get(field)
                    if not value:
                        continue
                    shown = True
                    if isinstance(value, list):
                        st.markdown(f"*{field}* · {len(value)} records")
                        st.dataframe(pd.DataFrame(value).astype(str), use_container_width=True)
                    elif str(value).lstrip().startswith(("{", "[")):
                        st.markdown(f"*{field}*")
                        st.code(str(value)[:20000], language="json")
                    else:
                        st.markdown(f"*{field}*")
                        st.write(str(value)[:20000])
                if not shown:
                    st.info("No output for this stage in the export (see the status above).")

with tabs[3]:
    st.subheader("Laclaudian discourse · step 6, and DNA · step 7")
    st.warning("Producer codes are candidate interpretations. Counts never prove hegemony, and a "
               "graph position is not evidence of guilt.")
    left, right = st.columns(2)
    with left:
        st.markdown("**Step 6 · Laclau status**")
        st.dataframe(status_counts(filtered, "laclau_status"), use_container_width=True)
        st.markdown("**Formula-of-populism conditions met**")
        st.dataframe(status_counts(filtered, "laclau_formula_conditions_met"), use_container_width=True)
        st.markdown("**Abstentions (producer)**")
        if "laclau_abstention_reason" in filtered:
            abstentions = filtered["laclau_abstention_reason"].map(clean)
            abstentions = abstentions[abstentions != ""]
            st.dataframe(abstentions.value_counts().rename_axis("reason").reset_index(name="records"),
                         use_container_width=True)
        else:
            st.info("This export carries no abstention column.")
    with right:
        st.markdown("**Step 7 · DNA status**")
        st.dataframe(status_counts(filtered, "dna_status"), use_container_width=True)
        statements = child_records(ROOT, filtered, "dna_statements_json")
        st.caption(f"{len(statements)} statements for the current selection, read from the text bundle.")
        if statements:
            actors = pd.DataFrame(statements).get("actor_name_raw", pd.Series(dtype=str)).map(clean)
            orgs = pd.DataFrame(statements).get("organization", pd.Series(dtype=str)).map(clean)
            layers = pd.DataFrame(statements).get("network_layer", pd.Series(dtype=str)).map(clean)
            chart(actors[actors != ""].value_counts().head(15), "Top actors in statements")
            chart(orgs[orgs != ""].value_counts().head(15), "Top organizations")
            chart(layers[layers != ""].value_counts(), "Discourse layers")
    statements = child_records(ROOT, filtered, "dna_statements_json")
    st.markdown("**Statements**")
    keys = [key for key in ("statement_id", "actor_name_raw", "concept", "stance", "agreement",
                            "organization", "evidence_quote")
            if statements and key in statements[0]]
    table([{"record_id": item["record_id"], "video_id": item.get("video_id", ""),
            **{key: clean(item.get(key))[:220] for key in keys}} for item in statements],
          "dna_table", caption="A statement is an interpretation of a text, never a fact about a person.")

with tabs[4]:
    st.subheader("Social network · step 8")
    st.caption("Only edges the producer wrote with a type and an evidence quote appear here; the "
               "graph is a reading aid, the edge table is the evidence.")
    edges = child_records(ROOT, filtered, "sna_edges_json")
    st.metric("Edges in the selection", f"{len(edges):,}")
    if not edges:
        st.info("No SNA edges for this selection. Step 8 is partial in this export — that is a "
                "coverage fact, not a finding about the corpus.")
    else:
        edge_frame = pd.DataFrame(edges).astype(str)
        left, right = st.columns(2)
        with left:
            chart(edge_frame["edge_type"].replace("", "not reported").value_counts().head(15),
                  "Edges by type")
            chart(pd.to_numeric(edge_frame["confidence"], errors="coerce").dropna()
                  .round(1).value_counts().sort_index(), "Edge confidence (rounded)")
        with right:
            chart(edge_frame["country"].replace("", "unknown").str.casefold().value_counts(),
                  "Edges by country")
            st.markdown("**Most connected nodes**")
            st.dataframe(node_degrees(edges), use_container_width=True)
        st.markdown("**Edges**")
        keys = [key for key in ("source", "target", "edge_type", "confidence", "evidence_quote")
                if key in edge_frame.columns]
        table([{"record_id": item["record_id"],
                **{key: clean(item.get(key))[:220] for key in keys}} for item in edges],
              "sna_table", caption="Every edge carries the quote it was drawn from.")

with tabs[5]:
    st.subheader("Aggregates over the current selection")
    st.caption("Counts over producer-coded fields. A sparse field means the stage did not run for "
               "that record, not that the entity is absent from the world.")
    left, right = st.columns(2)
    with left:
        chart(value_counts(filtered, "postprocess_entities", 15).set_index("value")["records"],
              "Top entities (summary stage)")
        chart(value_counts(filtered, "postprocess_themes", 15).set_index("value")["records"],
              "Top themes (summary stage)")
    with right:
        st.markdown("**Sentiment targets (producer-coded)**")
        st.dataframe(sentiment_totals(filtered), use_container_width=True)
        chart(value_counts(filtered, "asr_language", 10).set_index("value")["records"],
              "ASR language")
        chart(value_counts(filtered, "context_evidence_role", 10).set_index("value")["records"],
              "Evidence role")

with tabs[6]:
    st.subheader("Data quality — what this build changed, and why")
    counts = manifest.get("record_counts") or {}
    rows = [{"country": country, "read": data.get("read"), "exported": data.get("exported"),
             "duplicates removed": data.get("duplicate_rows"),
             "invalid ids removed": data.get("invalid_ids"),
             "DNA statements": data.get("dna_statement_rows")}
            for country, data in counts.items() if isinstance(data, dict)]
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.caption(f"Duplicate rule: identity is (country, video_id); the row carrying the most stage "
               f"output wins. Source bytes {sum(v.get('source_bytes', 0) for v in (manifest.get('countries') or {}).values()) / 1e6:.0f} MB "
               f"→ index + text bundle {sum(v.get('bytes', 0) for v in (manifest.get('outputs') or [])) / 1e6:.0f} MB.")
    dropped = (manifest.get("inputs") or {}).get("finland", {}).get("dropped_reasons") or {}
    st.markdown(f"**Dropped source columns ({len(dropped)}) and why**")
    st.dataframe(pd.DataFrame([{"column": key, "reason": value} for key, value in sorted(dropped.items())]),
                 use_container_width=True)
    failures = manifest.get("parse_failures") or {}
    if any(any(v.values()) for v in failures.values() if isinstance(v, dict)):
        st.warning("Unparseable JSON cells in the export: " + str(failures))
    else:
        st.success("Every structured child cell in the export parsed.")
    st.caption("The portugal CSV cannot be parsed as one stream (the producer's quoting merges "
               "records); the builder splits it on its own record boundary and asserts each block "
               "parses to the full field width. No row was dropped for that defect.")

with tabs[7]:
    st.subheader("Data and methods")
    for key in ("contract", "builder_version", "generated_at", "record_unit", "records", "read_only"):
        st.write(f"**{key}**: {manifest.get(key)}")
    st.markdown("**Derivations, stated once**")
    st.write({"record_date": "from the media id token YYYYMMDD — not a producer field",
              "month": "first seven characters of record_date",
              "pipeline_steps_ok": "count of step_01…step_07 statuses in ok/complete/cached",
              "has_sna": "step 8 edges present in the text bundle",
              "duplicates": "collapsed on (country, video_id), completeness-biased"})
    st.markdown("**Per-country source files**")
    st.dataframe(pd.DataFrame([{"country": country, **data}
                               for country, data in (manifest.get("countries") or {}).items()]),
                 use_container_width=True)
    st.caption("Nothing here is written back to the canonical records, and no chart is a finding: "
               "the status fields prove a stage ran, not that its interpretation is right.")
