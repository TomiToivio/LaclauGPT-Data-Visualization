from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

try:
    from .alignment_fix import reassign_empty_alignments
except ImportError:
    # Streamlit commonly executes this file as a script rather than as a
    # package module, so keep a local-import fallback for that launch mode.
    from alignment_fix import reassign_empty_alignments

try:
    from .pledge_search import SEARCH_SCOPES, search_frame
except ImportError:
    from pledge_search import SEARCH_SCOPES, search_frame

try:
    from .pledge_entities import merge_cell
except ImportError:
    from pledge_entities import merge_cell

BASE_DIR = Path(__file__).resolve().parent

REQUIRED_COLUMNS = [
    "video_id",
    "grievances",
    "topics",
    "entities",
    "themes",
    "persons",
    "positive",
    "neutral",
    "negative",
    "country",
    "political_alignment",
    "platform",
    "date",
]

# ── Purple haze / neon cyberpunk colour palette ─────────────────────────
NEIGN_BG = "#0a0015"
ALIGNMENT_COLORS = {
    "Far right": "#ff006e",
    "Red-green": "#06ffa5",
    "Centre right": "#ffbe0b",
    "Green left": "#8338ec",
    "Unknown": "#555555",
}
COUNTRY_COLORS = {
    "Finland": "#ff006e",
    "France": "#06ffa5",
    "Germany": "#ffbe0b",
    "Hungary": "#8338ec",
    "Poland": "#3a86ff",
    "Spain": "#fb5607",
    "Unknown": "#555555",
}
ALIGNMENT_ORDER = ["Far right", "Red-green", "Centre right", "Green left", "Unknown"]
COUNTRY_ORDER = ["Finland", "France", "Germany", "Hungary", "Poland", "Spain", "Unknown"]

#: Columns whose cells are comma-joined tag lists, merged on load (see pledge_entities).
MERGED_LABEL_COLUMNS = ("topics", "entities", "themes", "persons")


@st.cache_data
def load_data() -> pd.DataFrame:
    # Resolve data files relative to this script, not the caller's current
    # working directory. This makes both `streamlit run path/to/...py` and
    # package-root launches behave consistently.
    csv_path = BASE_DIR / "ep24_pledge_clean_v2.csv"
    if csv_path.exists():
        dataframe = pd.read_csv(csv_path, low_memory=False)
    else:
        import duckdb

        db_path = BASE_DIR / "dataframe.db"
        if not db_path.exists():
            raise FileNotFoundError(
                "Neither ep24_pledge_clean_v2.csv nor dataframe.db exists in "
                f"{BASE_DIR}"
            )
        con = duckdb.connect(str(db_path), read_only=True)
        try:
            dataframe = con.execute("SELECT * FROM ep24_pledge").df()
        finally:
            con.close()

    # Keep only the required schema and create missing columns as empty values.
    dataframe = dataframe.reindex(columns=REQUIRED_COLUMNS)

    dataframe["date"] = pd.to_datetime(dataframe["date"], errors="coerce")
    for col in REQUIRED_COLUMNS:
        if col != "date":
            dataframe[col] = dataframe[col].fillna("")
            # Treat NaN/None/nan strings as empty
            dataframe[col] = dataframe[col].astype(str).replace(
                {"nan": "", "NaN": "", "None": "", "<NA>": ""}
            )

    # Merge labels that mean the same thing: "eu" and "european union eu" are the European
    # Union, "politician" is "politicians". Merging happens on load, so every tab, filter and
    # count sees one tag per referent; the CSV on disk stays as the tagging model wrote it.
    for column in MERGED_LABEL_COLUMNS:
        dataframe[column] = dataframe[column].map(merge_cell)

    # Assign any empty (OT) political_alignment rows to their country's
    # underrepresented alignment and rewrite the OT token in video_id.
    # Idempotent -> no-op on data already fixed upstream (prepare_dataset /
    # puhti_grievances / pledge_to_duckdb). Kept here as defence in depth so
    # the Frequency chart (which groups by political_alignment) never silently
    # drops rows and undercounts a day.
    dataframe = reassign_empty_alignments(dataframe)

    # Final safety net: bucket any residual empty categorical as "Unknown" so
    # it is selectable in the sidebar and plotted, instead of being silently
    # dropped (e.g. a country whose rows are *all* empty-alignment, where no
    # least-populated target exists to reassign to).
    for _col in ("political_alignment", "country", "platform"):
        dataframe[_col] = dataframe[_col].replace("", "Unknown")

    return dataframe


def _value_counts_dataframe(values: pd.Series, index_name: str) -> pd.DataFrame:
    """Return a two-column count table with guaranteed unique column names.

    Avoid ``value_counts().reset_index()`` here.  Across pandas versions,
    the index and value Series can both inherit the source name (for
    example ``platform``), yielding duplicate columns that Plotly's
    Narwhals adapter correctly rejects.
    """
    value_counts = values.value_counts()
    return pd.DataFrame(
        {
            index_name: value_counts.index.to_numpy(),
            "count": value_counts.to_numpy(),
        }
    )


def _count_series_to_df(series: pd.Series, index_name: str) -> pd.DataFrame:
    counts = series.astype(str).str.strip()
    counts = counts[
        (counts != "")
        & (counts.str.lower() != "none")
        & (counts.str.lower() != "nan")
    ]
    return _value_counts_dataframe(counts, index_name)


def _count_tokens(series: pd.Series, index_name: str) -> pd.DataFrame:
    """Count individual tokens from a multi-value cell.

    The dataset stores topics / entities / sentiments as comma-separated lists
    (e.g. ``"european parliament elections, populism"``). Splitting on ``,`` /
    ``;`` and counting each token separately gives meaningful Top-N charts.
    The result is constructed explicitly so pandas cannot leak the source
    Series name into a duplicate output column.
    """
    tokens = series.astype(str).str.split(r"[;,]").explode().str.strip()
    tokens = tokens[
        (tokens != "")
        & (tokens.str.lower() != "none")
        & (tokens.str.lower() != "nan")
    ]
    return _value_counts_dataframe(tokens, index_name)


def dataframe_with_selections(df: pd.DataFrame, init_value: bool = False) -> pd.DataFrame:
    df_with_selections = df.copy()
    df_with_selections.insert(0, "Select", init_value)

    edited_df = st.data_editor(
        df_with_selections,
        hide_index=True,
        column_config={
            "Select": st.column_config.CheckboxColumn(
                label="Display Row",
                help="Select rows to view full details.",
                default=init_value,
                required=True,
            ),
            "themes": st.column_config.TextColumn(
                label="Themes",
                help="The political themes recognised in the video.",
            ),
            "persons": st.column_config.TextColumn(
                label="Persons",
                help="The persons recognised in the video.",
            ),
        },
        column_order=["Select"] + REQUIRED_COLUMNS,
        disabled=REQUIRED_COLUMNS,
        use_container_width=True,
    )

    return edited_df[edited_df["Select"]].drop(columns=["Select"])


def render_overview(filtered_df: pd.DataFrame, full_df: pd.DataFrame) -> None:
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "Frequency",
        "Grievances",
        "Topics",
        "Entities",
        "Themes",
        "Persons",
        "Sentiment",
    ])

    with tab1:
        st.subheader("Dataset Size")
        c1, c2 = st.columns(2)
        c1.metric("Total rows", len(full_df))
        c2.metric("Filtered rows", len(filtered_df))

        freq_df = filtered_df.dropna(subset=["date"]).copy()
        if not freq_df.empty:
            # --- Stacked bar: videos per day by alignment (fixes area chart
            # that silently dropped empty-alignment days).
            daily = freq_df.groupby(
                [freq_df["date"].dt.date, "political_alignment"]
            ).size().reset_index(name="count")
            daily["date"] = pd.to_datetime(daily["date"])
            aligns = sorted(
                daily["political_alignment"].unique(),
                key=lambda x: ALIGNMENT_ORDER.index(x) if x in ALIGNMENT_ORDER else 99,
            )
            fig = go.Figure()
            for align in aligns:
                sub = daily[daily["political_alignment"] == align]
                fig.add_trace(
                    go.Bar(
                        x=sub["date"],
                        y=sub["count"],
                        name=align,
                        marker_color=ALIGNMENT_COLORS.get(align, "#8338ec"),
                        hovertemplate="%{x|%b %d}<br>%{y} videos<br>"
                        + align
                        + "<extra></extra>",
                    )
                )
            fig.update_layout(
                barmode="stack",
                title="Daily videos by political alignment",
                xaxis_title="Date",
                yaxis_title="Count",
                plot_bgcolor=NEIGN_BG,
                paper_bgcolor=NEIGN_BG,
                font=dict(color="#e0aaff"),
                legend=dict(bgcolor="#1a0033", bordercolor="#4a0080"),
                xaxis=dict(tickformat="%b %d"),
            )
            st.plotly_chart(fig, use_container_width=True)

            # --- Stacked bar: videos per day by country.
            daily_c = freq_df.groupby(
                [freq_df["date"].dt.date, "country"]
            ).size().reset_index(name="count")
            daily_c["date"] = pd.to_datetime(daily_c["date"])
            countries = sorted(
                daily_c["country"].unique(),
                key=lambda x: COUNTRY_ORDER.index(x) if x in COUNTRY_ORDER else 99,
            )
            fig2 = go.Figure()
            for country in countries:
                sub = daily_c[daily_c["country"] == country]
                fig2.add_trace(
                    go.Bar(
                        x=sub["date"],
                        y=sub["count"],
                        name=country,
                        marker_color=COUNTRY_COLORS.get(country, "#8338ec"),
                        hovertemplate="%{x|%b %d}<br>%{y} videos<br>"
                        + country
                        + "<extra></extra>",
                    )
                )
            fig2.update_layout(
                barmode="stack",
                title="Daily videos by country",
                xaxis_title="Date",
                yaxis_title="Count",
                plot_bgcolor=NEIGN_BG,
                paper_bgcolor=NEIGN_BG,
                font=dict(color="#e0aaff"),
                legend=dict(bgcolor="#1a0033", bordercolor="#4a0080"),
                xaxis=dict(tickformat="%b %d"),
            )
            st.plotly_chart(fig2, use_container_width=True)

            # --- Heatmap: country x alignment totals.
            heat = (
                freq_df.groupby(["country", "political_alignment"])
                .size()
                .unstack(fill_value=0)
            )
            heat = heat.reindex(
                index=[c for c in COUNTRY_ORDER if c in heat.index],
                columns=[a for a in ALIGNMENT_ORDER if a in heat.columns],
            )
            fig3 = go.Figure(
                data=go.Heatmap(
                    z=heat.values,
                    x=heat.columns,
                    y=heat.index,
                    # Magma's high end is pale yellow, so the white cell labels disappeared there
                    # ("light colour on light colour"). A dark-only ramp keeps every value legible
                    # whatever theme the researcher's browser is in, and matches the app's palette.
                    colorscale=[[0.0, "#12002a"], [0.5, "#4a0080"], [1.0, "#9d4edd"]],
                    text=heat.values,
                    texttemplate="%{text}",
                    textfont=dict(color="white", size=14),
                    hovertemplate="%{y} / %{x}<br>%{z} videos<extra></extra>",
                )
            )
            fig3.update_layout(
                title="Total videos: country x alignment",
                plot_bgcolor=NEIGN_BG,
                paper_bgcolor=NEIGN_BG,
                font=dict(color="#e0aaff"),
                xaxis_title="Political alignment",
                yaxis_title="Country",
            )
            st.plotly_chart(fig3, use_container_width=True)

        platform_counts = _count_series_to_df(filtered_df["platform"], "platform")
        if not platform_counts.empty:
            st.subheader("Platform Distribution")
            fig4 = px.bar(
                platform_counts,
                x="platform",
                y="count",
                title="Rows by platform",
                color_discrete_sequence=["#06ffa5"],
            )
            fig4.update_layout(
                plot_bgcolor=NEIGN_BG,
                paper_bgcolor=NEIGN_BG,
                font=dict(color="#e0aaff"),
            )
            st.plotly_chart(fig4, use_container_width=True)

    with tab2:
        st.subheader("Grievances")
        g = filtered_df["grievances"].astype(str).str.strip()
        g = g[(g != "") & (g.str.lower() != "none") & (g.str.lower() != "nan")]
        st.write(f"{len(g)} videos have extracted grievances for the current filters.")
        if g.empty:
            st.info("No grievance data available for current filters.")
        else:
            # Grievances are free text and nearly unique, so a count bar chart
            # is uninformative; show a readable, researcher-controlled sample instead.
            # 50 was a hard ceiling: the list is the only place the wording appears.
            unique = g.drop_duplicates().tolist()
            limit = st.slider(
                "How many grievances to list", min_value=50, max_value=max(50, min(len(unique), 2000)),
                value=min(max(50, 200), max(50, len(unique))), step=50, key="grievance_limit",
            )
            for i, txt in enumerate(unique[:limit], 1):
                st.markdown(f"{i}. {txt}")
            if limit < len(unique):
                st.caption(f"Showing {limit} of {len(unique)} distinct grievances; raise the slider to see more.")

    with tab3:
        st.subheader("Top Topics")
        topic_counts = _count_tokens(filtered_df["topics"], "topic")
        if topic_counts.empty:
            st.info("No topic data available for current filters.")
        else:
            fig = px.bar(
                topic_counts.head(20),
                x="topic",
                y="count",
                title="Top 20 topics",
                color_discrete_sequence=["#ffbe0b"],
            )
            fig.update_layout(
                plot_bgcolor=NEIGN_BG,
                paper_bgcolor=NEIGN_BG,
                font=dict(color="#e0aaff"),
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab4:
        st.subheader("Top Entities")
        entity_counts = _count_tokens(filtered_df["entities"], "entity")
        if entity_counts.empty:
            st.info("No entity data available for current filters.")
        else:
            fig = px.bar(
                entity_counts.head(20),
                x="entity",
                y="count",
                title="Top 20 entities",
                color_discrete_sequence=["#3a86ff"],
            )
            fig.update_layout(
                plot_bgcolor=NEIGN_BG,
                paper_bgcolor=NEIGN_BG,
                font=dict(color="#e0aaff"),
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab5:
        st.subheader("Top Themes")
        theme_counts = _count_tokens(filtered_df["themes"], "theme")
        if theme_counts.empty:
            st.info("No theme data available for current filters.")
        else:
            fig = px.bar(
                theme_counts.head(20),
                x="theme",
                y="count",
                title="Top 20 themes",
                color_discrete_sequence=["#fb5607"],
            )
            fig.update_layout(
                plot_bgcolor=NEIGN_BG,
                paper_bgcolor=NEIGN_BG,
                font=dict(color="#e0aaff"),
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab6:
        st.subheader("Top Persons")
        person_counts = _count_tokens(filtered_df["persons"], "person")
        if person_counts.empty:
            st.info("No person data available for current filters.")
        else:
            fig = px.bar(
                person_counts.head(20),
                x="person",
                y="count",
                title="Top 20 persons",
                color_discrete_sequence=["#8ac926"],
            )
            fig.update_layout(
                plot_bgcolor=NEIGN_BG,
                paper_bgcolor=NEIGN_BG,
                font=dict(color="#e0aaff"),
            )
            st.plotly_chart(fig, use_container_width=True)

    with tab7:
        st.subheader("Sentiment")
        pos = _count_tokens(filtered_df["positive"], "positive")
        neu = _count_tokens(filtered_df["neutral"], "neutral")
        neg = _count_tokens(filtered_df["negative"], "negative")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("**Positive**")
            st.dataframe(pos.head(15), use_container_width=True, hide_index=True)
        with c2:
            st.markdown("**Neutral**")
            st.dataframe(neu.head(15), use_container_width=True, hide_index=True)
        with c3:
            st.markdown("**Negative**")
            st.dataframe(neg.head(15), use_container_width=True, hide_index=True)


def ep2024_dashboard(df: pd.DataFrame) -> None:
    filtered_df = df.copy()

    st.sidebar.subheader("Filters")

    search_query = st.sidebar.text_input(
        "Search (universal number, grievance, topic, entity, theme or person)"
    )
    search_scope = st.sidebar.selectbox(
        "Search in", list(SEARCH_SCOPES), index=0,
        help="Universal number searches video_id, e.g. HEPP24-ES-CR-IG-20240520-1081000.",
    )

    country_options = sorted(
        filtered_df["country"]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    country_filter = st.sidebar.multiselect(
        "Country", options=country_options, default=country_options
    )
    if country_filter:
        filtered_df = filtered_df[filtered_df["country"].isin(country_filter)]

    alignment_options = sorted(
        filtered_df["political_alignment"]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    alignment_filter = st.sidebar.multiselect(
        "Political alignment", options=alignment_options, default=alignment_options
    )
    if alignment_filter:
        filtered_df = filtered_df[
            filtered_df["political_alignment"].isin(alignment_filter)
        ]

    platform_options = sorted(
        filtered_df["platform"]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
        .tolist()
    )
    platform_filter = st.sidebar.multiselect(
        "Platform", options=platform_options, default=platform_options
    )
    if platform_filter:
        filtered_df = filtered_df[filtered_df["platform"].isin(platform_filter)]

    date_min = filtered_df["date"].min()
    date_max = filtered_df["date"].max()
    if pd.notna(date_min) and pd.notna(date_max):
        date_range = st.sidebar.date_input(
            "Date range",
            value=(date_min.date(), date_max.date()),
            min_value=date_min.date(),
            max_value=date_max.date(),
        )
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df = filtered_df[
                (filtered_df["date"] >= pd.to_datetime(start_date))
                & (filtered_df["date"] <= pd.to_datetime(end_date))
            ]

    if search_query:
        filtered_df = search_frame(filtered_df, search_query, search_scope)

    selection = dataframe_with_selections(filtered_df)

    if not selection.empty:
        st.subheader("Selected Row Details")
        for _, row in selection.iterrows():
            with st.expander(f"Video {row['video_id']}", expanded=True):
                st.markdown(f"**Video ID:** {row['video_id']}")
                st.markdown(f"**Date:** {row['date']}")
                st.markdown(f"**Country:** {row['country']}")
                st.markdown(f"**Political Alignment:** {row['political_alignment']}")
                st.markdown(f"**Platform:** {row['platform']}")
                st.markdown(f"**Grievances:** {row['grievances']}")
                st.markdown(f"**Topics:** {row['topics']}")
                st.markdown(f"**Entities:** {row['entities']}")
                st.markdown(f"**Themes:** {row['themes']}")
                st.markdown(f"**Persons:** {row['persons']}")
                st.markdown(f"**Positive:** {row['positive']}")
                st.markdown(f"**Neutral:** {row['neutral']}")
                st.markdown(f"**Negative:** {row['negative']}")
    else:
        render_overview(filtered_df, df)


st.set_page_config(
    page_title="Pledge Video Analysis Dashboard",
    page_icon=":alien:",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "mailto:tomi.toivio@helsinki.fi",
        "Report a bug": "mailto:tomi.toivio@helsinki.fi",
        "About": "Developed by Tomi Toivio, University of Helsinki.",
    },
)

with (BASE_DIR / "auth.yaml").open(encoding="utf-8") as file:
    config = yaml.load(file, Loader=SafeLoader)

authenticator = stauth.Authenticate(
    config["credentials"],
    config["cookie"]["name"],
    config["cookie"]["key"],
    config["cookie"]["expiry_days"],
)

df = load_data()

st.title("Pledge Video Analysis Dashboard")

# No CSV export from the UI: hide the dataframes' "Download as CSV" toolbar
# button. Streamlit exposes no switch for it, so it is hidden with CSS. The
# rows still reach the browser to draw the table, so this removes the one-click
# export affordance, not the access.
st.markdown(
    """
    <style>
    [data-testid="stElementToolbar"] button[aria-label="Download as CSV"],
    [data-testid="stElementToolbar"] button[aria-label*="Download"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    authenticator.login()
except Exception as e:
    st.error(e)

if st.session_state.get("authentication_status"):
    ep2024_dashboard(df)
elif st.session_state.get("authentication_status") is False:
    st.error("Username/password is incorrect")
elif st.session_state.get("authentication_status") is None:
    st.warning("Please enter your username and password")

logo_path = BASE_DIR / "logo.png"
if logo_path.is_file():
    st.image(str(logo_path))
st.caption("Pledge Video Analysis Dashboard")