import pandas as pd
import plotly.colors as pc
import plotly.graph_objects as go
import streamlit as st  # type: ignore[import-not-found]

from src.calculations import (
    calculate_points_progression,
    calculate_standings,
    get_all_matches,
)


_ESHG_TEAM = "Don Quishoot H3"
_ESHG_LINE_COLOR = "#2E7D32"
_STANDING_COLUMNS = ["Pos", "Team", "GS", "PT", "W", "G", "V", "DV", "DT", "DS"]
_DISPLAY_COLUMNS = ["Pos", "Verschil", *_STANDING_COLUMNS[1:]]

_OTHER_TEAM_COLORS = [
    "#2563EB",  # blauw
    "#EA580C",  # oranje
    "#DC2626",  # rood
    "#7C3AED",  # paars
    "#0891B2",  # cyaan
    "#D97706",  # amber
    "#DB2777",  # magenta
    "#4F46E5",  # indigo
    "#0D9488",  # teal
    "#64748B",  # leigrijs
    "#9333EA",  # violet
]


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


def _render_points_progression(matches: list[dict]) -> None:
    st.subheader("Puntenverloop")

    col_mode, col_filter = st.columns([1.15, 2.35], vertical_alignment="bottom")
    with col_mode:
        view_mode = st.radio(
            "X-as weergave",
            options=["Gespeelde wedstrijden (GS)", "Speelronde"],
            index=0,
            horizontal=True,
            key="points_progression_mode",
        )

    is_round_mode = view_mode == "Speelronde"
    progression = calculate_points_progression(
        matches, mode="rounds" if is_round_mode else "matches"
    )
    if progression.empty:
        st.info("Er zijn nog geen gespeelde wedstrijden om een puntenverloop te tonen.")
        return

    # Vaste volgorde op actuele ranglijst (Pos 1 t/m 11)
    standings_order_df = (
        progression[["Team", "Positie"]]
        .drop_duplicates()
        .sort_values("Positie", kind="stable")
    )
    all_teams = standings_order_df["Team"].tolist()
    position_map = dict(
        zip(standings_order_df["Team"], standings_order_df["Positie"])
    )

    with col_filter:
        selected_raw = st.multiselect(
            "Selecteer teams",
            options=all_teams,
            default=all_teams,
            key="points_progression_teams",
            help="Standaard worden alle teams getoond. Verwijder teams om direct concurrenten te vergelijken.",
        )

    if not selected_raw:
        st.info("Selecteer minimaal één team om het puntenverloop weer te bekijken.")
        return

    # Herstel altijd de vaste ranglijst-sortering ongeacht aanklikvolgorde
    selected_set = set(selected_raw)
    selected_teams = [team for team in all_teams if team in selected_set]

    if is_round_mode:
        st.caption(
            "● Gespeelde wedstrijd · ○ Vrij of nog niet gespeelde inhaalwedstrijd"
        )
    else:
        st.caption(
            "Elke stap op de X-as is één gespeelde wedstrijd (GS). Teams met minder gespeelde wedstrijden hebben een kortere lijn."
        )

    filtered = progression[progression["Team"].isin(selected_teams)]
    max_step = int(filtered["Stap"].max())
    max_points = int(filtered["Punten"].max())
    y_upper = max(max_points + 2, 3)
    y_dtick = 3 if y_upper <= 36 else 6

    palette = _OTHER_TEAM_COLORS + pc.qualitative.Set3
    color_index = 0
    team_colors: dict[str, str] = {}
    for team in all_teams:
        if team == _ESHG_TEAM:
            team_colors[team] = _ESHG_LINE_COLOR
        else:
            team_colors[team] = palette[color_index % len(palette)]
            color_index += 1

    fig = go.Figure()

    # Teken ESHG als laatste trace zodat de groene lijn bovenop andere lijnen ligt,
    # maar behoud de ranglijstvolgorde in de legenda via legendrank.
    draw_order = [t for t in selected_teams if t != _ESHG_TEAM]
    if _ESHG_TEAM in selected_teams:
        draw_order.append(_ESHG_TEAM)

    for team in draw_order:
        team_df = filtered[filtered["Team"] == team].sort_values("Stap")
        is_eshg = team == _ESHG_TEAM
        pos = int(position_map[team])
        color = team_colors[team]

        marker_symbols = [
            "circle" if bool(played) else "circle-open"
            for played in team_df["Gespeeld"]
        ]
        marker_sizes = [
            (8 if is_eshg else 5.5) if bool(played) else (7.5 if is_eshg else 6)
            for played in team_df["Gespeeld"]
        ]

        fig.add_trace(
            go.Scatter(
                x=team_df["Stap"],
                y=team_df["Punten"],
                mode="lines+markers",
                name=f"{pos}. {team}",
                legendrank=pos,
                customdata=team_df["Detail"],
                line={
                    "color": color,
                    "width": 3.5 if is_eshg else 1.8,
                },
                marker={
                    "symbol": marker_symbols,
                    "size": marker_sizes,
                    "color": color,
                    "line": {"width": 2, "color": color},
                },
                opacity=1.0 if is_eshg else 0.78,
                xhoverformat=(
                    f"<b>{pos}. {team}</b>: <b>%{{y}} pt</b> — %{{customdata}}"
                    "<extra></extra>"
                ),
            )
        )

    # Eindlabel voor Don Quishoot H3 rechts naast het laatste datapunt
    if _ESHG_TEAM in selected_set:
        eshg_df = filtered[filtered["Team"] == _ESHG_TEAM].sort_values("Stap")
        if not eshg_df.empty:
            last_row = eshg_df.iloc[-1]
            fig.add_annotation(
                x=float(last_row["Stap"]),
                y=float(last_row["Punten"]),
                text=f" {int(last_row['Punten'])} pt",
                showarrow=False,
                xanchor="left",
                yanchor="middle",
                font={
                    "color": _ESHG_LINE_COLOR,
                    "size": 12,
                    "family": "sans-serif",
                },
            )

    x_axis_title = "Speelronde" if is_round_mode else "Gespeelde wedstrijden (GS)"
    x_hover_title = "Ronde %{x}" if is_round_mode else "Na %{x} gespeelde wedstrijden"

    fig.update_layout(
        height=490,
        margin={"l": 10, "r": 35, "t": 15, "b": 15},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        hoverlabel={
            "bgcolor": "rgba(24, 24, 27, 0.92)",
            "bordercolor": "rgba(255, 255, 255, 0.15)",
            "font": {"color": "#F4F4F5", "size": 12},
        },
        xaxis={
            "title": x_axis_title,
            "range": [-0.2, max_step + 0.65],
            "dtick": 1,
            "showgrid": False,
            "zeroline": False,
            "hoverformat": "d",
        },
        yaxis={
            "title": "Punten",
            "range": [0, y_upper],
            "dtick": y_dtick,
            "rangemode": "tozero",
            "showgrid": True,
            "gridcolor": "rgba(128, 128, 128, 0.18)",
            "zeroline": True,
            "zerolinecolor": "rgba(128, 128, 128, 0.3)",
        },
        legend={
            "title": {"text": "Stand"},
            "itemclick": "toggle",
            "itemdoubleclick": "toggleothers",
            "bgcolor": "rgba(0,0,0,0)",
        },
    )
    fig.update_xaxes(hoverformat=f"<b>{x_hover_title}</b><extra></extra>")

    st.plotly_chart(
        fig,
        width="stretch",
        config={"displayModeBar": False},
    )


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
            height=(len(standings) + 1) * 36,
        )

    _render_points_progression(matches)

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