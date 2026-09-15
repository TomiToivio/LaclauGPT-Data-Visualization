"""Pure monitor/explore view-model transformations; counts are descriptive only."""
from __future__ import annotations
import pandas as pd
from .data import explode_labels

def monitor(frame: pd.DataFrame) -> dict[str, object]:
    time = pd.to_datetime(frame.get("source_timestamp"), errors="coerce", utc=True)
    return {"documents":len(frame),"awaiting_review":int((frame.get("review_status",pd.Series("pending",index=frame.index))!="verified").sum()),"latest_source":time.max().isoformat() if len(time) and pd.notna(time.max()) else "","formations":explode_labels(frame,"formations"),"signifiers":explode_labels(frame,"signifiers"),"actors":explode_labels(frame,"entities")}

def relations(frame: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for _, row in frame.iterrows():
        for relation in row.get("relations",[]) if isinstance(row.get("relations",[]),list) else []:
            if isinstance(relation,dict): rows.append({"source":relation.get("source",""),"target":relation.get("target",""),"type":relation.get("type",""),"document_id":row.get("document_id","")})
    return pd.DataFrame(rows,columns=["source","target","type","document_id"])
