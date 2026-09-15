import pandas as pd

from laclaugpt_visualization.legacy_ep24 import adapt
from laclaugpt_visualization.review import Review, SQLiteReviewStore
from laclaugpt_visualization.transforms import graph_projection, monitor, relations


def test_monitor_relations_and_review(tmp_path):
    frame = pd.DataFrame(
        [
            {
                "document_id": "synthetic://1",
                "source_url": "synthetic://1",
                "source_timestamp": "2026-01-01T00:00:00Z",
                "analysis_timestamp": "2026-01-02T00:00:00Z",
                "analysis_status": "analyzed",
                "review_status": "PROVISIONAL",
                "formations": ["synthetic formation"],
                "signifiers": ["future"],
                "entities": ["synthetic actor"],
                "source_author": "synthetic actor",
                "relations": [
                    {"source_ref": "future", "target_ref": "actor", "relation_type": "equivalence"}
                ],
            }
        ]
    )
    view = monitor(frame)
    assert view["documents"] == 1
    assert view["analyzed"] == 1
    assert len(relations(frame)) == 1
    assert graph_projection(frame)["nodes"]

    store = SQLiteReviewStore(tmp_path / "reviews.sqlite3")
    store.save(Review(source_url="synthetic://1", status="ACCEPTED", note="synthetic"))
    saved = store.get("synthetic://1")
    assert saved is not None
    assert saved.status == "ACCEPTED"
    assert saved.document_id == "synthetic://1"

    legacy = adapt({"video_id": "v1", "platform": "synthetic"})
    assert legacy["document_id"] == "legacy:ep24:v1"
    assert legacy["source_url"] == "legacy:ep24:v1"
    assert legacy["source_native_ids"]["video_id"] == "v1"
