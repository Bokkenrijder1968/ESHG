import pandas as pd
import streamlit as st

from src.calculations import calculate_standings, get_all_matches


_ESHG_TEAM = "Don Quishoot H3"
_STANDING_COLUMNS = ["Pos", "Team", "GS", "PT", "W", "G", "V", "DV", "DT", "DS"]
_DISPLAY_COLUMNS = ["Pos", "Verschil", *_STANDING_COLUMNS[1:]]


def _highlight_eshg(row: pd.Series) -> list[str]:
    if row["Team"] == _ESHG_TEAM:
        return ["background-color: rgba(46, 125, 50, 0.25); font-weight: bold"] * len(row)
    return [""] * len(row)


def _position_changes(matches: list[dict], standings: pd.DataFrame) -> dict[str, str]:
    latest_played_date: dict[str, str] = {}
    for match in matches:
        if match.get("gespeeld") is not True:
            continue
        if match.get("score_thuis") is None or match.get("score_uit") is None:
            continue
        match_date = str(match.get("datum", ""))
        for team in (str(match.get("thuis", "")), str(match.get("uit", ""))):
            if team and match_date > latest_played_date.get(team, ""):
                latest_played_date[team] = match_date

    changes: dict[str, str] = {}
    for row in standings.to_dict("records"):
        team = str(row["Team"])
        last_date = latest_played_date.get(team)
        if last_date is None:
            changes[team] = "—"
            continue

        prior_matches = [
            match
            for match in matches
            if match.get("gespeeld") is True
            and match.get("score_thuis") is not None
            and match.get("score_uit") is not None
            and str(match.get("datum", "")) < last_date
        ]
        previous_standings = calculate_standings(prior_matches)
        previous_positions = {
            str(previous_row["Team"]): int(previous_row["Pos"])
            for previous_row in previous_standings.to_dict("records")
        }
        previous_position = previous_positions.get(team)
        if previous_position is None:
            changes[team] = "—"
            continue

        movement = previous_position - int(row["Pos"])
        if movement > 0:
            changes[team] = f"▲ {movement}"
        elif movement < 0:
            changes[team] = f"▼ {abs(movement)}"
        else:
            changes[team] = "↔"
    return changes


def render_table_view() -> None:
    st.title("Stand & Schema")

    try:
        matches = get_all_matches()
        standings = calculate_standings(matches)
    except ValueError as error:
        st.error(f"De stand en het programma konden niet worden geladen: {error}")
        return

    st.subheader("Competitiestand")
    if standings.empty:
        st.info("Er zijn nog geen gespeelde wedstrijden voor de stand.")
        st.dataframe(
            pd.DataFrame(columns=_DISPLAY_COLUMNS),
            hide_index=True,
            column_order=_DISPLAY_COLUMNS,
            width="stretch",
        )
    else:
        st.caption(
            "Verschil vergeleken met de positie vóór de meest recente gespeelde speelronde "
            "van elk team. Een streepje betekent dat er nog geen eerdere positie is."
        )
        display_standings = standings.copy()
        position_changes = _position_changes(matches, standings)
        display_standings.insert(
            1,
            "Verschil",
            display_standings["Team"].map(position_changes).fillna("—"),
        )
        styled_standings = display_standings.style.apply(_highlight_eshg, axis=1)
        st.dataframe(
            styled_standings,
            hide_index=True,
            column_order=_DISPLAY_COLUMNS,
            width="stretch",
        )

    played_matches = sorted(
        (match for match in matches if match.get("gespeeld") is True),
        key=lambda match: str(match.get("datum", "")),
        reverse=True,
    )
    planned_matches = [
        match for match in matches if match.get("gespeeld") is False
    ]

    with st.expander("Gespeelde uitslagen", expanded=False):
        if played_matches:
            results = pd.DataFrame(
                [
                    {
                        "Datum": match.get("datum", ""),
                        "Thuis": match.get("thuis", ""),
                        "Score": (
                            f"{match.get('score_thuis')} - {match.get('score_uit')}"
                            if match.get("score_thuis") is not None
                            and match.get("score_uit") is not None
                            else "—"
                        ),
                        "Uit": match.get("uit", ""),
                    }
                    for match in played_matches
                ],
                columns=["Datum", "Thuis", "Score", "Uit"],
            )
            st.dataframe(results, hide_index=True, width="stretch")
        else:
            st.info("Er zijn nog geen gespeelde wedstrijden.")

    with st.expander("Resterend programma", expanded=False):
        teams = sorted(
            {
                team
                for match in matches
                for team in (str(match.get("thuis", "")), str(match.get("uit", "")))
                if team
            }
        )
        team_options = teams or [_ESHG_TEAM]
        selected_team = st.selectbox(
            "Toon programma voor team",
            team_options,
            index=(
                team_options.index(_ESHG_TEAM)
                if _ESHG_TEAM in team_options
                else 0
            ),
            key="remaining_schedule_team",
        )
        filtered_matches = sorted(
            (
                match
                for match in planned_matches
                if selected_team in (match.get("thuis"), match.get("uit"))
            ),
            key=lambda match: str(match.get("datum", "")),
        )
        if filtered_matches:
            schedule = pd.DataFrame(
                [
                    {
                        "Datum": match.get("datum", ""),
                        "Thuis": match.get("thuis", ""),
                        "Uit": match.get("uit", ""),
                    }
                    for match in filtered_matches
                ],
                columns=["Datum", "Thuis", "Uit"],
            )
            st.dataframe(schedule, hide_index=True, width="stretch")
        else:
            st.info(f"Geen resterende wedstrijden gevonden voor {selected_team}.")
