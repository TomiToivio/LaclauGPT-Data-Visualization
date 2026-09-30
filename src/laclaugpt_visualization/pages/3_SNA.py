"""Streamlit entry point for the Phase 2 SNA workspace."""
import streamlit as st

from laclaugpt_visualization.sna_page import render_sna_workspace

st.set_page_config(page_title="Phase 2 SNA", layout="wide")
st.title("LaclauGPT Data Visualization")
render_sna_workspace()
