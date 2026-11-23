import pandas as pd
import plotly.express as px
import streamlit as st  # type: ignore[import-not-found]

from src.calculations import (
    _ESHG_TEAM,
    _get_scoring_matches,
    _match_has_result,
    _normalize_date,
    _person_name,
    _score,
    _team_key,
    get_corner_stats,
    get_goal_type_distribution,
    get_quarter_stats,
)


def _coverage_label(tracked: int, total: int) -> str:
    if total <= 0:
        return "Geen gespeelde wedstrijden"
    return f"{tracked} van {total} wedstrijden"


def _quarter_strength(quarter_stats: pd.DataFrame, strongest: bool) -> str:
    if quarter_stats.empty or not (
        quarter_stats["Goals ESHG"].sum() or quarter_stats["Goals Tegen"].sum()
    ):
        return "—"
    target = (
        quarter_stats["Doelsaldo"].max()
        if strongest
        else quarter_stats["Doelsaldo"].min()
    )
    quarters = quarter_stats.loc[
        quarter_stats["Doelsaldo"] == target, "Kwart"
    ].tolist()
    return ", ".join(quarters)


def _resolve_opponent_and_score(match: dict) -> tuple[str, str]:
    home = str(match.get("thuis", "")).strip()
    away = str(match.get("uit", "")).strip()
    home_score = _score(match.get("score_thuis"))
    away_score = _score(match.get("score_uit"))

    opponent = _person_name(match.get("tegenstander"))
    if _team_key(home) == _team_key(_ESHG_TEAM):
        if not opponent:
            opponent = away
        score_text = (
            f"{home_score} - {away_score}"
            if home_score is not None and away_score is not None
            else "—"
        )
    else:
        if not opponent:
            opponent = home
        score_text = (
            f"{away_score} - {home_score}"
            if home_score is not None and away_score is not None
            else "—"
        )
    return opponent, score_text


def _quarter_match_timeline(matches: list[dict]) -> pd.DataFrame:
    rows = []
    for match in matches:
        if not _match_has_result(match):
            continue
        if match.get("kwarten_bijgehouden") is False:
            continue
        quarters = match.get("kwarten")
        if not isinstance(quarters, dict):
            continue
        eshg_quarters = quarters.get("eshg")
        opponent_quarters = quarters.get("tegenstander")
        if not isinstance(eshg_quarters, list) or not isinstance(
            opponent_quarters, list
        ):
            continue
        if len(eshg_quarters) != 4 or len(opponent_quarters) != 4:
            continue

        opponent, score_text = _resolve_opponent_and_score(match)
        row: dict[str, object] = {
            "Datum": _normalize_date(match.get("datum")),
            "Tegenstander": opponent,
            "Eindstand": score_text,
        }
        eshg_scores = []
        opponent_scores = []
        for index in range(4):
            eshg_value = eshg_quarters[index] if index < len(eshg_quarters) else 0
            opponent_value = (
                opponent_quarters[index] if index < len(opponent_quarters) else 0
            )
            try:
                eshg_score = max(0, int(eshg_value))
                opponent_score = max(0, int(opponent_value))
            except (TypeError, ValueError):
                eshg_score = opponent_score = 0
            eshg_scores.append(eshg_score)
            opponent_scores.append(opponent_score)
            row[f"Q{index + 1} ESHG"] = eshg_score
            row[f"Q{index + 1} Tegen"] = opponent_score
        row["1e helft"] = sum(eshg_scores[:2]) - sum(opponent_scores[:2])
        row["2e helft"] = sum(eshg_scores[2:4]) - sum(opponent_scores[2:4])
        rows.append(row)

    rows.sort(key=lambda row: str(row["Datum"]), reverse=True)
    return pd.DataFrame(
        rows,
        columns=[
            "Datum",
            "Tegenstander",
            "Eindstand",
            "Q1 ESHG",
            "Q1 Tegen",
            "Q2 ESHG",
            "Q2 Tegen",
            "Q3 ESHG",
            "Q3 Tegen",
            "Q4 ESHG",
            "Q4 Tegen",
            "1e helft",
            "2e helft",
        ],
    )


def render_trends_view() -> None:
    st.title("Teamstatistieken")
    try:
        quarter_stats = get_quarter_stats()
        corner_stats = get_corner_stats()
        goal_distribution = get_goal_type_distribution()
        matches = _get_scoring_matches()
    except ValueError as error:
        st.error(f"De teamstatistieken konden niet worden geladen: {error}")
        return

    total_played = int(corner_stats.get("wedstrijden_totaal", len(matches)))
    corners_tracked = int(corner_stats.get("wedstrijden_bijgehouden", 0))
    quarters_tracked = int(quarter_stats.attrs.get("wedstrijden_bijgehouden", 0))

    corner_coverage = _coverage_label(corners_tracked, total_played)
    quarter_coverage = _coverage_label(quarters_tracked, total_played)

    kpi_columns = st.columns(4)
    kpi_columns[0].metric(
        "Strafcorner Rendement ESHG",
        f"{corner_stats['conversie_percentage']:.1f}%",
        delta=corner_coverage,
        delta_color="off",
    )
    kpi_columns[1].metric(
        "Strafcorner Verdediging",
        f"{corner_stats['verdedigingspercentage']:.1f}%",
        delta=corner_coverage,
        delta_color="off",
    )
    kpi_columns[2].metric(
        "Sterkste Kwart",
        _quarter_strength(quarter_stats, strongest=True),
        delta=quarter_coverage,
        delta_color="off",
    )
    kpi_columns[3].metric(
        "Zwakste Kwart",
        _quarter_strength(quarter_stats, strongest=False),
        delta=quarter_coverage,
        delta_color="off",
    )

    st.subheader("Doelpunten per kwart")
    st.caption(f"Gebaseerd op {quarter_coverage}.")
    quarter_chart_data = quarter_stats.melt(
        id_vars=["Kwart"],
        value_vars=["Goals ESHG", "Goals Tegen"],
        var_name="Team",
        value_name="Goals",
    )
    quarter_chart = px.bar(
        quarter_chart_data,
        x="Kwart",
        y="Goals",
        color="Team",
        barmode="group",
        category_orders={"Kwart": ["Q1", "Q2", "Q3", "Q4"]},
        color_discrete_map={
            "Goals ESHG": "#2E7D32",
            "Goals Tegen": "#E76F51",
        },
        labels={"Goals": "Doelpunten", "Team": ""},
    )
    quarter_chart.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 10, "r": 10, "t": 15, "b": 10},
        yaxis={
            "dtick": 1,
            "gridcolor": "rgba(128, 128, 128, 0.18)",
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    st.plotly_chart(
        quarter_chart,
        width="stretch",
        config={"displayModeBar": False},
    )

    st.subheader("Doelpuntenverdeling (Veld vs Corner)")
    st.caption(f"Gebaseerd op alle {total_played} gespeelde wedstrijden.")
    nonzero_distribution = goal_distribution.loc[goal_distribution["Aantal"] > 0]
    if nonzero_distribution.empty:
        st.info("Er zijn nog geen doelpunten naar type geregistreerd.")
    else:
        goal_type_chart = px.pie(
            nonzero_distribution,
            names="Type",
            values="Aantal",
            hole=0.5,
            color="Type",
            color_discrete_map={
                "Veldgoal": "#2E7D32",
                "Strafcorner": "#2563EB",
                "Strafbal (PS)": "#D97706",
            },
        )
        goal_type_chart.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin={"l": 10, "r": 10, "t": 15, "b": 10},
        )
        st.plotly_chart(
            goal_type_chart,
            width="stretch",
            config={"displayModeBar": False},
        )

    st.subheader("Seizoensverloop per kwart")
    timeline = _quarter_match_timeline(matches)
    if timeline.empty:
        st.info("Er zijn nog geen kwartstanden per gespeelde wedstrijd geregistreerd.")
    else:
        st.caption(
            f"Gebaseerd op {quarter_coverage}. "
            "De kolommen 1e helft en 2e helft tonen het doelsaldo van ESHG per wedstrijd."
        )
        st.dataframe(timeline, hide_index=True, width="stretch")