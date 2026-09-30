from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RDF_PAGE = ROOT / "src" / "laclaugpt_visualization" / "pages" / "rdf_explorer.py"


def test_phase2_rdf_explorer_exposes_analysis_owned_stage_filter() -> None:
    source = RDF_PAGE.read_text(encoding="utf-8")
    compile(source, str(RDF_PAGE), "exec")

    assert '"Research stage"' in source
    assert '"stage": _clean(stage_filter)' in source
    assert 'node.get("stage") or node.get("layer")' in source
    assert "Visualization does not infer" not in source  # semantics stay upstream, not reimplemented here
