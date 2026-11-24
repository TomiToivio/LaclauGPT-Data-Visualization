"""Standalone, server-local Streamlit entry point."""
import hashlib
import itertools
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from lab import CATEGORIES, FIELDS, connect, csv_bytes, curated_rows, current, read_rows, save, validate_export

st.set_page_config(page_title="Legacy EP24 Merge Lab", layout="wide")
st.title("Legacy EP24 Merge Lab")
root = Path(os.environ["EP24_PRIVATE_CHECKOUT"])
db, area = connect(root)
revision, state = current(db)
groups, aliases, names = (state[k] for k in ("groups", "aliases", "names"))
owner = {key: group for group, members in groups.items() for key in members}
original = {}
for key, alias in aliases.items():
    original.setdefault(alias["initial"], set()).add(owner[key])
pending = set()
for a, b in state["candidates"]:
    for x, y in itertools.product(original[a], original[b]):
        if x != y and not any((set(groups[x]).intersection(left) and set(groups[y]).intersection(right))
                              or (set(groups[y]).intersection(left) and set(groups[x]).intersection(right))
                              for left, right in state["separate"]):
            pending.add(tuple(sorted((x, y))))
priority = set(itertools.chain.from_iterable(pending))
st.caption(f"Revision {revision} · {state['reviewed']} decisions reviewed · {len(pending)} candidate pairs remaining")
total = len(state["candidates"])
if total:
    st.progress(max(0., 1 - len(pending) / total))
if state["reviewed"] and state["reviewed"] % 10 == 0:
    st.success("Review batch complete")


def commit(action, *args):
    try:
        save(db, revision, action, args)
    except ValueError as exc:
        st.error(str(exc))
    else:
        st.rerun()


for col, action in zip(st.columns(2), ("undo", "redo")):
    if col.button(action.title(), key=f"{action}{revision}"):
        commit(action)

cards = components.declare_component("ep24_merge_cards", path=str(Path(__file__).parent / "cards"))
for tab, category in zip(st.tabs(CATEGORIES), CATEGORIES):
    with tab:
        ids = [g for g in groups if FIELDS[aliases[groups[g][0]]["field"]][0] == category]
        rows = {}
        for g in ids:
            members = [aliases[k] for k in groups[g]]
            refs = {s: ctx for m in members for s, ctx in m["refs"].items()}
            rows[g] = (members, refs)
        query = st.text_input("Search names and aliases", key=category+"q").casefold()
        c1, c2, c3 = st.columns(3)
        facets = [sorted({ctx[i] for _, refs in rows.values() for ctx in refs.values() if ctx[i]}) for i in (0, 1)]
        country = c1.multiselect("Country", facets[0], key=category+"country")
        lang = c2.multiselect("Language", facets[1], key=category+"lang")
        minimum = c3.number_input("Minimum source records", min_value=1, key=category+"min")
        ceiling = st.slider("Maximum automatic match score", 0., 1., 1., key=category+"score")
        uncertain = st.checkbox("Only unresolved candidates", key=category+"uncertain")
        ids = [g for g in ids if (not uncertain or g in priority) and len(rows[g][1]) >= minimum
               and min(m["confidence"] for m in rows[g][0]) <= ceiling
               and any((not country or ctx[0] in country) and (not lang or ctx[1] in lang) for ctx in rows[g][1].values())
               and any(query in x.casefold() for x in [names[g]] + [m["label"] for m in rows[g][0]])]
        ids.sort(key=lambda g: (g not in priority, -len(rows[g][1]), names[g], g))
        page = st.number_input("Batch", 1, max(1, (len(ids)+23)//24), key=category+"batch")
        visible = ids[(page-1)*24:page*24]
        pairs = sorted((a, b) for a, b in pending if a in visible or b in visible)
        if pairs:
            pair = st.selectbox("Suggested pair", pairs, format_func=lambda pair: " ↔ ".join(names[g] for g in pair), key=category+"pair")
            if st.button("Preview suggested pair", key=category+"preview"):
                st.session_state[category+"selected"] = list(pair)
        items = [dict(id=g, name=names[g], detail=f"{len(rows[g][1])} records · {rows[g][0][0]['field']} · "
                      + ("review candidate" if g in priority else rows[g][0][0]["reason"])
                      + f" · score {min(m['confidence'] for m in rows[g][0]):.2f} · " + ", ".join(sorted({m["label"] for m in rows[g][0]})[:3])) for g in visible]
        event = cards(cards=items, revision=revision, key=category+"cards")
        selection = category+"selected"
        if event and event.get("revision") == revision and event.get("nonce") != st.session_state.get(category+"last"):
            proposed = event.get("ids", [])
            if len(proposed) == 2 and all(g in visible for g in proposed):
                st.session_state[selection] = proposed
            st.session_state[category+"last"] = event.get("nonce")
        choices = list(dict.fromkeys(visible + [g for g in st.session_state.get(selection, []) if g in rows]))
        selected = st.multiselect("Select clusters to preview (keyboard or drag)", choices,
                                  format_func=lambda g: names[g]+" · "+g[:6], key=selection)
        if selected:
            refs = {s: ctx for g in selected for s, ctx in rows[g][1].items()}
            st.write(f"{len(selected)} clusters → 1 proposed cluster · {len(refs)} distinct affected records")
            before = sum(len(rows[g][1]) for g in selected)
            st.caption(f"Record–label links: {before} → {len(refs)}. Shared records count once after merging.")
            if len(selected) > 1:
                neighbors = Counter()
                for other, (_, observations) in rows.items():
                    if other not in selected:
                        together = len(refs.keys() & observations.keys())
                        if together:
                            neighbors[names[other]] += together
                if neighbors:
                    st.table([{"Co-occurring cluster": n, "Shared records after merge": count}
                              for n, count in neighbors.most_common(5)])
            st.write(sorted({m["label"] for g in selected for m in rows[g][0]}))
            st.table([dict(source=s, context=ctx[2][:300]) for s, ctx in list(refs.items())[:4]])
            label = st.text_input("Canonical label", names[selected[0]], key=category+selected[0]+str(revision))
            if len(selected) > 1:
                if st.button("Confirm merge", key=category+"merge"+str(revision)):
                    commit("merge", selected, label)
                if st.button("Reject and keep separate", key=category+"reject"+str(revision)):
                    commit("separate", selected)
            else:
                if st.button("Rename", key=category+"rename"+str(revision)):
                    commit("rename", selected, label)
                member = st.selectbox("Alias to split", groups[selected[0]], format_func=lambda k: aliases[k]["label"]+" · "+k[:6], key=category+"member")
                if st.button("Split selected alias", key=category+"split"+str(revision)):
                    commit("split", selected, label, member)

st.subheader("Versioned export")
approved = st.checkbox("I approve this mapping for export", key=f"approve{revision}")
destination = area / "exports" / f"revision-{revision}"
if st.button("Export approved version", disabled=not approved or destination.exists()):
    import shutil
    destination.parent.mkdir(exist_ok=True)
    temp = Path(tempfile.mkdtemp(dir=destination.parent))
    try:
        manifest = dict(schema="legacy-ep24-dashboard-csv-v1", mapping_version=revision,
                        source_sha256=state["inputs"], review_status="researcher-approved",
                        remaining_candidates=len(pending), export_sha256={}, record_counts={})
        for name in state["inputs"]:
            source = root / "analysis/ep24/source" / name
            manifest["record_counts"][name] = sum(1 for _ in read_rows(source))
            data = csv_bytes(curated_rows(source, state))
            (temp / name).write_bytes(data)
            manifest["export_sha256"][name] = hashlib.sha256(data).hexdigest()
        (temp / "mapping.json").write_text(json.dumps(state, ensure_ascii=False))
        (temp / "manifest.json").write_text(json.dumps(manifest, indent=2))
        validate_export(temp)
        temp.rename(destination)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    st.success(f"Saved revision {revision}")
if destination.is_dir():
    for path in sorted(destination.iterdir()):
        st.download_button("Download "+path.name, path.read_bytes(), file_name=path.name)
