"""Phase 1 isolated Discourse Network Analysis visualization page."""
from pathlib import Path

import pandas as pd
import streamlit as st

from laclaugpt_visualization.app import _load_default_frame
from laclaugpt_visualization.config import get_settings
from laclaugpt_visualization.dna_page import render_dna_workspace

st.set_page_config(page_title="Discourse Network Analysis", layout="wide")
st.title("LaclauGPT Data Visualization")
settings = get_settings()
settings.ensure_local_directories()
frame = _load_default_frame()
if frame is None:
    frame = pd.DataFrame()

roots = [Path(settings.data_dir)]
if settings.analysis_data_dir is not None:
    roots.insert(0, Path(settings.analysis_data_dir))

render_dna_workspace(frame, roots)
