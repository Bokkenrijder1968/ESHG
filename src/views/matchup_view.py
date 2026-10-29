import math
from typing import Any

import pandas as pd
import streamlit as st

from src.calculations import (
    _common_opponents_expected_diff,
    _team_recent_averages,
    _team_match_result,
    get_all_matches,
    get_common_opponents_comparison,
    get_head_to_head,
    get_opponents_by_schedule,
    get_opponent_form,
)
from src.constants import OPPONENTS


_ESHG_TEAM = "Don Quishoot H3"
_RESULT_COLORS = {"W": "#198754", "G": "#6c757d", "V": "#dc3545"}


def _team_averages(
    matches: list[dict[str, Any]], team: str
) -> tuple[float, float, int]:
    played = [
        result
        for match in matches
        if (result := _team_match_result(match, team)) is not None
    ]
    if not played:
        return 0.0, 0.0, 0

    return (
        sum(match["doelpunten_voor"] for match in played) / len(played),
        sum(match["doelpunten_tegen"] for match in played) / len(played),
        len(played),
    )


def _poisson_probabilities(expected_goals: float) -> list[float]:
    max_goals = min(
        100,
        max(12, math.ceil(expected_goals + 8 * math.sqrt(expected_goals + 1))),
    )
    probabilities = [math.exp(-expected_goals)]
    for goals in range(1, max_goals + 1):
        probabilities.append(
            probabilities[-1] * expected_goals / goals
        )
    return probabilities


def _render_prediction(matches: list[dict[str, Any]], opponent: str) -> None:
    model = st.radio(
        "Rekenmodel",
        [
            "Seizoensgemiddelde (Standaard)",
            "Recente Vorm (Laatste 3 wedstrijden)",
            "Gedeelde Tegenstanders",
            "Gecombineerd Ensemble",
        ],
        horizontal=True,
        key="matchup_prediction_model",
    )
    eshg_scored, eshg_conceded, eshg_played = _team_averages(matches, _ESHG_TEAM)
    opponent_scored, opponent_conceded, opponent_played = _team_averages(
        matches, opponent
    )
    if not eshg_played or not opponent_played:
        st.info("Er zijn nog onvoldoende gespeelde wedstrijden voor een voorspelling.")
        return

    seasonal_expected_eshg = (eshg_scored + opponent_conceded) / 2
    seasonal_expected_opponent = (opponent_scored + eshg_conceded) / 2
    recent_eshg_scored, recent_eshg_conceded = _team_recent_averages(
        matches, _ESHG_TEAM
    )
    recent_opponent_scored, recent_opponent_conceded = _team_recent_averages(
        matches, opponent
    )
    recent_expected_eshg = (
        recent_eshg_scored + recent_opponent_conceded
    ) / 2
    recent_expected_opponent = (
        recent_opponent_scored + recent_eshg_conceded
    ) / 2
    relative_difference = _common_opponents_expected_diff(
        matches, _ESHG_TEAM, opponent
    )
    common_expected_eshg = max(0.0, 2.5 + relative_difference / 2)
    common_expected_opponent = max(0.0, 2.5 - relative_difference / 2)

    if model == "Recente Vorm (Laatste 3 wedstrijden)":
        expected_eshg = recent_expected_eshg
        expected_opponent = recent_expected_opponent
    elif model == "Gedeelde Tegenstanders":
        expected_eshg = common_expected_eshg
        expected_opponent = common_expected_opponent
    elif model == "Gecombineerd Ensemble":
        expected_eshg = (
            0.40 * common_expected_eshg
            + 0.35 * recent_expected_eshg
            + 0.25 * seasonal_expected_eshg
        )
        expected_opponent = (
            0.40 * common_expected_opponent
            + 0.35 * recent_expected_opponent
            + 0.25 * seasonal_expected_opponent
        )
    else:
        expected_eshg = seasonal_expected_eshg
        expected_opponent = seasonal_expected_opponent

    eshg_probabilities = _poisson_probabilities(expected_eshg)
    opponent_probabilities = _poisson_probabilities(expected_opponent)
    win_probability = sum(
        eshg_chance * sum(opponent_probabilities[:goals])
        for goals, eshg_chance in enumerate(eshg_probabilities)
    )
    draw_probability = sum(
        eshg_chance * opponent_probabilities[goals]
        for goals, eshg_chance in enumerate(eshg_probabilities)
        if goals < len(opponent_probabilities)
    )
    loss_probability = max(0.0, 1 - win_probability - draw_probability)
    st.metric(
        "Verwachte uitslag",
        f"{round(expected_eshg)} - {round(expected_opponent)}",
        help=(
            f"Doelpuntenverwachting: ESHG {expected_eshg:.1f} – "
            f"{opponent} {expected_opponent:.1f}"
        ),
    )
    st.caption(
        f"Indicatieve kansen · model: {model} (Poisson-verdeling): "
        f"ESHG winst {win_probability:.0%} · gelijk {draw_probability:.0%} · "
        f"{opponent} winst {loss_probability:.0%}."
    )


def render_matchup_view() -> None:
    st.title("🎯 Matchup & Analyse")
    try:
        matches = get_all_matches()
    except ValueError as error:
        st.error(f"De wedstrijdgegevens konden niet worden geladen: {error}")
        return

    upcoming = sorted(
        (
            match
            for match in matches
            if match.get("gespeeld") is False
            and _ESHG_TEAM
            in (str(match.get("thuis", "")), str(match.get("uit", "")))
        ),
        key=lambda match: str(match.get("datum", "")),
    )
    next_opponent = None
    if upcoming:
        fixture = upcoming[0]
        next_opponent = (
            fixture["uit"]
            if fixture["thuis"] == _ESHG_TEAM
            else fixture["thuis"]
        )
    opponent_options = get_opponents_by_schedule(list(OPPONENTS))
    default_opponent = (
        next_opponent if next_opponent in OPPONENTS else opponent_options[0]
    )
    opponent = st.selectbox(
        "Tegenstander",
        opponent_options,
        index=opponent_options.index(default_opponent),
        key="matchup_opponent",
        help="Geordend op datum van de eerstvolgende geplande wedstrijd.",
    )

    st.subheader("Vorm van de tegenstander")
    form = get_opponent_form(opponent)
    if form:
        badges = " ".join(
            (
                f'<span style="display:inline-block;background:{_RESULT_COLORS[match["resultaat"]]};'
                f'color:white;border-radius:12px;padding:4px 10px;margin:2px">'
                f'{match["resultaat"]} · {match["datum"]} · {match["score"]}</span>'
            )
            for match in form
        )
        st.markdown(badges, unsafe_allow_html=True)
        goals_for = sum(match["doelpunten_voor"] for match in form) / len(form)
        goals_against = sum(match["doelpunten_tegen"] for match in form) / len(form)
        st.caption(
            f"Laatste {len(form)} gespeelde wedstrijd(en): gemiddeld "
            f"{goals_for:.1f} doelpunten voor en {goals_against:.1f} tegen per wedstrijd."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Datum": match["datum"],
                        "Tegen wie": match["tegenstander"],
                        "Thuis/uit": match["locatie"],
                        "Score": match["score"],
                        "Resultaat": match["resultaat"],
                    }
                    for match in form
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.info(f"Er zijn nog geen gespeelde wedstrijden van {opponent} bekend.")

    st.subheader("Onderlinge historie (H2H)")
    try:
        head_to_head = get_head_to_head(opponent)
    except ValueError as error:
        st.error(f"De onderlinge historie kon niet worden geladen: {error}")
        head_to_head = {
            "gespeeld": 0,
            "winst": 0,
            "gelijk": 0,
            "verlies": 0,
            "doelsaldo": 0,
            "wedstrijden": [],
        }

    st.caption(
        f"{head_to_head['gespeeld']} gespeeld · {head_to_head['winst']} winst · "
        f"{head_to_head['gelijk']} gelijk · {head_to_head['verlies']} verlies · "
        f"doelsaldo {head_to_head['doelsaldo']:+d}"
    )
    previous_matches = head_to_head["wedstrijden"]
    if previous_matches:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Datum": match["datum"],
                        "Locatie": match["locatie"],
                        "Uitslag": match["score"],
                        "Resultaat": match["resultaat"],
                    }
                    for match in previous_matches
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        for match in previous_matches:
            notes = match.get("notities", {})
            extra_stats = match.get("extra_stats", {})
            tactics = str(notes.get("tactiek", "")).strip()
            evaluation = str(notes.get("evaluatie", "")).strip()
            cards = str(extra_stats.get("kaarten", "")).strip()
            substitutes = str(extra_stats.get("invallers", "")).strip()
            saved_notes = [
                f"**Speelstijl (press / zone / corners):** {tactics}" if tactics else "",
                f"**Leerpunten:** {evaluation}" if evaluation else "",
                f"**Extra statistieken – kaarten:** {cards}" if cards else "",
                f"**Invallers / afwezigen:** {substitutes}" if substitutes else "",
            ]
            note_text = "\n\n".join(note for note in saved_notes if note)
            if note_text:
                with st.expander(f"Notities vorige ontmoeting · {match['datum']}"):
                    st.info(note_text)
    else:
        st.info(f"Er zijn nog geen eerdere ontmoetingen met {opponent}.")

    st.subheader("Vergelijking via gedeelde tegenstanders")
    try:
        comparison = get_common_opponents_comparison(opponent)
    except ValueError as error:
        st.error(f"De vergelijking kon niet worden geladen: {error}")
        comparison = pd.DataFrame(
            columns=["Gedeeld Team", "Uitslag ESHG", "Uitslag Tegenstander"]
        )
    if comparison.empty:
        st.info("Er zijn nog geen gedeelde tegenstanders met bekende uitslagen.")
    else:
        st.dataframe(comparison, hide_index=True, width="stretch")

    st.subheader("Statistische voorspelling")
    _render_prediction(matches, opponent)
