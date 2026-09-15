import pandas as pd
from laclaugpt_visualization.review import Review, SQLiteReviewStore
from laclaugpt_visualization.transforms import monitor, relations
from laclaugpt_visualization.legacy_ep24 import adapt

def test_monitor_relations_and_review(tmp_path):
    frame=pd.DataFrame([{"document_id":"synthetic-1","source_timestamp":"2026-01-01T00:00:00Z","formations":["synthetic formation"],"signifiers":["future"],"entities":["synthetic actor"],"relations":[{"source":"future","target":"actor","type":"equivalence"}]}])
    view=monitor(frame); assert view["documents"]==1; assert len(relations(frame))==1
    store=SQLiteReviewStore(tmp_path/'reviews.sqlite3'); store.save(Review(document_id='synthetic-1',status='verified',note='synthetic'))
    assert store.get('synthetic-1').status=='verified'
    assert adapt({'video_id':'v1','platform':'synthetic'} )['document_id']=='v1'
