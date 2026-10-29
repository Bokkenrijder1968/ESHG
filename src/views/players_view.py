import pandas as pd
import plotly.express as px
import streamlit as st

from src.calculations import (
    calculate_player_stats,
    get_player_match_timeline,
    get_top_duos,
)


_PLAYER_TABLE_COLUMNS = [
    "Positie",
    "Speler",
    "Goals",
    "Assists",
    "Totaal",
    "Veldgoals",
    "Strafcorners",
]


def _leader(stats: pd.DataFrame, column: str) -> tuple[str, int]:
    if stats.empty:
        return "—", 0
    leader = stats.sort_values(
        [column, "Speler"],
        ascending=[False, True],
        kind="stable",
    ).iloc[0]
    score = int(leader[column])
    return (str(leader["Speler"]), score) if score else ("—", 0)


def render_players_view() -> None:
    st.title("Spelers & Stats")

    try:
        stats = calculate_player_stats()
        top_duos = get_top_duos()
    except ValueError as error:
        st.error(f"De spelersstatistieken konden niet worden geladen: {error}")
        return

    top_scorer, goal_count = _leader(stats, "Goals")
    assist_king, assist_count = _leader(stats, "Assists")
    mvp, mvp_count = _leader(stats, "Totaal_G_A")

    scorer_column, assist_column, mvp_column = st.columns(3)
    with scorer_column:
        st.metric(
            "Topscorer",
            top_scorer,
            f"{goal_count} goals" if goal_count else "0 goals",
        )
    with assist_column:
        st.metric(
            "Assistkoning",
            assist_king,
            f"{assist_count} assists" if assist_count else "0 assists",
        )
    with mvp_column:
        st.metric(
            "Meest Waardevolle Speler / MVP",
            mvp,
            f"{mvp_count} G+A" if mvp_count else "0 G+A",
        )

    st.subheader("Topscorers & assists")
    table = stats.rename(columns={"Totaal_G_A": "Totaal"})[
        _PLAYER_TABLE_COLUMNS
    ]
    st.dataframe(table, hide_index=True, width="stretch")

    st.subheader("Goals & assists per speler")
    involved_players = stats.loc[stats["Totaal_G_A"] > 0].copy()
    if involved_players.empty:
        st.info("Er zijn nog geen doelpunten of assists geregistreerd.")
    else:
        chart_data = involved_players.melt(
            id_vars=["Speler"],
            value_vars=["Goals", "Assists"],
            var_name="Type",
            value_name="Aantal",
        )
        chart = px.bar(
            chart_data,
            x="Aantal",
            y="Speler",
            color="Type",
            orientation="h",
            barmode="stack",
            category_orders={
                "Speler": list(reversed(involved_players["Speler"].tolist())),
                "Type": ["Goals", "Assists"],
            },
            labels={"Aantal": "Aantal", "Speler": "Speler"},
        )
        st.plotly_chart(chart, width="stretch")

    st.subheader("Gouden duo's")
    if top_duos.empty:
        st.info("Er zijn nog geen goals met assist geregistreerd.")
    else:
        st.dataframe(top_duos, hide_index=True, width="stretch")

    st.subheader("Spelersdetails")
    selected_player = st.selectbox(
        "Selecteer een speler",
        stats["Speler"].tolist(),
        key="player_stats_selection",
    )
    try:
        timeline = get_player_match_timeline(selected_player)
    except ValueError as error:
        st.error(f"De wedstrijdtijdlijn kon niet worden geladen: {error}")
        return
    if timeline.empty:
        st.info(f"Voor {selected_player} zijn nog geen goals of assists geregistreerd.")
    else:
        st.dataframe(timeline, hide_index=True, width="stretch")
