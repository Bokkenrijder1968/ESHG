import pandas as pd
import streamlit as st

from src.calculations import get_all_matches, simulate_standings


_ESHG_TEAM = "Don Quishoot H3"
_DISPLAY_COLUMNS = ["Pos", "Verschil", "Team", "GS", "PT", "DS"]


def _planned_matches(matches: list[dict]) -> list[dict]:
    planned_matches = [
        match for match in matches if match.get("gespeeld") is False
    ]
    return planned_matches


def _round_number(match: dict) -> int | None:
    value = match.get("ronde")
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        round_number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round_number if round_number > 0 else None


def _matches_for_selection(
    planned_matches: list[dict],
    selection: str,
) -> list[dict]:
    if selection == "Volgende speelronde":
        available_rounds = [
            round_number
            for match in planned_matches
            if (round_number := _round_number(match)) is not None
        ]
        if not available_rounds:
            return []
        next_round = min(available_rounds)
        return [
            match
            for match in planned_matches
            if _round_number(match) == next_round
        ]

    if not planned_matches:
        return []
    next_date = min(str(match.get("datum", "")) for match in planned_matches)
    return [
        match for match in planned_matches if str(match.get("datum", "")) == next_date
    ]


def _difference_label(value: object) -> str:
    if pd.isna(value):
        return "—"
    difference = int(value)
    if difference > 0:
        return f"🟢 ▲ {difference}"
    if difference < 0:
        return f"🔴 ▼ {abs(difference)}"
    return "⚪ ="


def _highlight_eshg(row: pd.Series) -> list[str]:
    if row["Team"] == _ESHG_TEAM:
        return ["background-color: rgba(46, 125, 50, 0.25); font-weight: bold"] * len(row)
    return [""] * len(row)


def _render_conclusion(
    standings: pd.DataFrame,
    simulated_matches: list[dict],
) -> None:
    eshg_row = standings.loc[standings["Team"] == _ESHG_TEAM]
    if eshg_row.empty:
        st.info("Don Quishoot H3 staat nog niet in de berekende ranglijst.")
        return

    row = eshg_row.iloc[0]
    current_position = (
        int(row["Pos"]) + int(row["Pos_Verschil"])
        if not pd.isna(row["Pos_Verschil"])
        else None
    )
    new_position = int(row["Pos"])
    difference = (
        int(row["Pos_Verschil"]) if not pd.isna(row["Pos_Verschil"]) else None
    )
    if current_position is None:
        st.info(f"Don Quishoot H3 komt virtueel uit op plek {new_position}.")
        return

    result_match = next(
        (
            match
            for match in simulated_matches
            if _ESHG_TEAM in (match["thuis"], match["uit"])
        ),
        None,
    )
    if result_match:
        score = (
            f"{result_match['score_thuis']} - {result_match['score_uit']}"
        )
        if difference is None:
            conclusion = (
                f"Bij een {score} uitslag komt Don Quishoot H3 uit op plek "
                f"{new_position}."
            )
        elif difference > 0:
            conclusion = (
                f"Bij een {score} uitslag stijgt Don Quishoot H3 van plek "
                f"{current_position} naar plek {new_position} ({difference:+d})."
            )
        elif difference < 0:
            conclusion = (
                f"Bij een {score} uitslag daalt Don Quishoot H3 van plek "
                f"{current_position} naar plek {new_position} ({difference:+d})."
            )
        else:
            conclusion = (
                f"Bij een {score} uitslag blijft Don Quishoot H3 op plek "
                f"{new_position}."
            )
    elif difference:
        movement = "stijgt" if difference > 0 else "daalt"
        conclusion = (
            f"Don Quishoot H3 {movement} van plek {current_position} naar plek "
            f"{new_position} ({difference:+d})."
        )
    else:
        conclusion = (
            f"Don Quishoot H3 blijft op plek {new_position}."
            if difference == 0
            else f"Don Quishoot H3 komt uit op plek {new_position}."
        )

    passed_teams = standings.loc[
        (standings["Pos"] > new_position)
        & (standings["Pos_Verschil"].notna())
        & (
            standings["Pos"] + standings["Pos_Verschil"]
            < current_position
        )
    ]
    if not passed_teams.empty:
        passed_team = passed_teams.iloc[0]
        reason = (
            " op doelsaldo"
            if (
                int(row["PT"]) == int(passed_team["PT"])
                and int(row["W"]) == int(passed_team["W"])
                and int(row["DS"]) != int(passed_team["DS"])
            )
            else ""
        )
        conclusion += f" Het passeert {passed_team['Team']}{reason}."
    st.markdown(conclusion)


def render_scenario_view() -> None:
    st.title("🔮 Scenario Calculator")

    try:
        matches = get_all_matches()
    except ValueError as error:
        st.error(f"Het wedstrijdprogramma kon niet worden geladen: {error}")
        return

    planned_matches = _planned_matches(matches)
    if not planned_matches:
        st.info("Er zijn geen geplande wedstrijden om te simuleren.")
        return

    selection = st.radio(
        "Wedstrijden selecteren op",
        ["Eerstvolgende datum", "Volgende speelronde"],
        horizontal=True,
        key="scenario_selection",
    )
    selection_mode = (
        "Volgende speelronde"
        if selection == "Volgende speelronde"
        else "Eerstvolgende datum"
    )
    selected_matches = _matches_for_selection(planned_matches, selection_mode)
    if not selected_matches:
        st.info(
            "Er zijn geen geplande wedstrijden met een speelronde. "
            "Voeg een geplande wedstrijd toe en ken een speelronde toe, of kies "
            "‘Eerstvolgende datum’."
        )
        return

    if selection_mode == "Volgende speelronde":
        selected_round = _round_number(selected_matches[0])
        st.subheader(f"Volgende speelronde · {selected_round}")
        unassigned_count = sum(
            _round_number(match) is None for match in planned_matches
        )
        if unassigned_count:
            st.caption(
                f"{unassigned_count} geplande wedstrijd(en) zonder speelronde "
                "worden niet meegenomen in deze simulatie."
            )
    else:
        st.subheader(f"Eerstvolgende wedstrijddatum · {selected_matches[0].get('datum', 'onbekend')}")

    mode = st.radio(
        "Simulatiemodus",
        ["Volledige speelronde", "Snelle simulatie alleen voor ESHG"],
        horizontal=True,
        key="scenario_mode",
    )
    simulated_matches: list[dict] = []

    if mode == "Snelle simulatie alleen voor ESHG":
        eshg_matches = [
            match
            for match in selected_matches
            if _ESHG_TEAM in (match.get("thuis"), match.get("uit"))
        ]
        if not eshg_matches:
            st.info("Don Quishoot H3 speelt niet in deze speelronde.")
            return
        for index, match in enumerate(eshg_matches):
            st.markdown(f"**{match['thuis']} - {match['uit']}**")
            home_column, away_column = st.columns(2)
            with home_column:
                home_score = st.number_input(
                    "Score Thuis",
                    min_value=0,
                    step=1,
                    key=f"scenario_quick_home_{index}",
                )
            with away_column:
                away_score = st.number_input(
                    "Score Uit",
                    min_value=0,
                    step=1,
                    key=f"scenario_quick_away_{index}",
                )
            simulated_matches.append(
                {
                    **match,
                    "score_thuis": int(home_score),
                    "score_uit": int(away_score),
                    "gespeeld": True,
                }
            )
    else:
        for index, match in enumerate(selected_matches):
            st.markdown(
                f"**{match.get('datum', '')} · {match['thuis']} - {match['uit']}**"
            )
            include_match = st.checkbox(
                "Neem deze uitslag mee",
                key=f"scenario_include_{index}",
            )
            home_column, away_column = st.columns(2)
            with home_column:
                home_score = st.number_input(
                    "Score Thuis",
                    min_value=0,
                    step=1,
                    key=f"scenario_home_{index}",
                )
            with away_column:
                away_score = st.number_input(
                    "Score Uit",
                    min_value=0,
                    step=1,
                    key=f"scenario_away_{index}",
                )
            if include_match:
                simulated_matches.append(
                    {
                        **match,
                        "score_thuis": int(home_score),
                        "score_uit": int(away_score),
                        "gespeeld": True,
                    }
                )

    if st.button("Bereken Virtuele Stand", type="primary"):
        if not simulated_matches:
            st.session_state.pop("scenario_standings", None)
            st.session_state.pop("scenario_matches", None)
            st.warning("Selecteer of vul minimaal één uitslag in om te simuleren.")
        else:
            try:
                st.session_state["scenario_standings"] = simulate_standings(
                    simulated_matches
                )
            except ValueError as error:
                st.error(f"De virtuele stand kon niet worden berekend: {error}")
            else:
                st.session_state["scenario_matches"] = simulated_matches

    standings = st.session_state.get("scenario_standings")
    if isinstance(standings, pd.DataFrame):
        st.subheader("Virtuele ranglijst")
        display_standings = standings.copy()
        display_standings["Verschil"] = display_standings["Pos_Verschil"].map(
            _difference_label
        )
        display_standings = display_standings[_DISPLAY_COLUMNS]
        st.dataframe(
            display_standings.style.apply(_highlight_eshg, axis=1),
            hide_index=True,
            width="stretch",
        )
        st.subheader("Conclusie")
        _render_conclusion(
            standings,
            st.session_state.get("scenario_matches", []),
        )
