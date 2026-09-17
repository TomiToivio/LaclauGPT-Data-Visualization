"""AI26 multimethod Explore page in the unified Streamlit workbench."""
from pathlib import Path

import streamlit as st

from laclaugpt_visualization.app import _load_default_frame
from laclaugpt_visualization.config import get_settings
from laclaugpt_visualization.multimethod_page import render_ai26_multimethod_workspace

st.set_page_config(page_title="AI26 multi-method Explore", layout="wide")
st.title("LaclauGPT Data Visualization")
settings = get_settings()
settings.ensure_local_directories()
frame = _load_default_frame()
if frame is None:
    import pandas as pd
    frame = pd.DataFrame()
roots = [Path(settings.data_dir)]
if settings.analysis_data_dir is not None:
    roots.insert(0, Path(settings.analysis_data_dir))
render_ai26_multimethod_workspace(frame, roots)
