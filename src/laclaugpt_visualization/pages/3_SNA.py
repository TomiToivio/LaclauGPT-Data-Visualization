"""Streamlit entry point for the Phase 2 SNA workspace."""
import streamlit as st

from laclaugpt_visualization.demo_auth import require_login
from laclaugpt_visualization.sna_page import render_sna_workspace

st.set_page_config(page_title="Phase 2 SNA", layout="wide")
# Security gate (#263): the multipage nav reaches every script directly, so each page gates itself before it
# reads anything. A session that authenticated on the main page stays authenticated here.
require_login()
st.title("LaclauGPT Data Visualization")
render_sna_workspace()
