from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st  # type: ignore[import-not-found]

from src.calculations import (
    calculate_elo_ratings,
    calculate_monte_carlo_history,
    calculate_next_match_impact,
    calculate_standings,
    get_all_matches,
    run_monte_carlo_simulation,
)


_ESHG_TEAM = "Don Quishoot H3"
_ESHG_COLOR = "#2E7D32"
_PERCENT_COLUMNS = [
    "Kampioenschap (%)",
    "Top 3 (%)",
    "Degradatiekans (%)",
    "Linkerrijtje (%)",
]

_PERCENT_POSITION = [
    "Plek 1 (%)",
    "Plek 2 (%)",
    "Plek 3 (%)",
    "Plek 4 (%)",
    "Plek 5 (%)",
    "Plek 6 (%)",
    "Plek 7 (%)",
    "Plek 8 (%)",
    "Plek 9 (%)",
    "Plek 10 (%)",
    "Plek 11 (%)",
]

_THRESHOLD_COLORS = {
    "Plek 1": "#1D4ED8",
    "Plek 2": "#2563EB",
    "Plek 3": "#0284C7",
    "Plek 4": "#0D9488",
    "Plek 5": "#65A30D",
    "Plek 6": "#D97706",
    "Plek 7": "#EA580C",
    "Plek 8": "#64748B",
    "Plek 9": "#9333EA",
    "Plek 10": "#DC2626",
    "Plek 11": "#991B1B",
}

_THRESHOLD_SUFFIXES = {
    "Plek 1": " (kampioen)",
    "Plek 3": " (top 3)",
    "Plek 6": " (linkerrijtje)",
    "Plek 10": " (degradatiegrens)",
}


def _subtle_difference_color(difference: float) -> str:
    if difference > 0:
        return "background-color: rgba(25, 135, 84, 0.10)"
    if difference < 0:
        return "background-color: rgba(220, 53, 69, 0.10)"
    return ""


@st.cache_data(show_spinner=False)
def _cached_monte_carlo(
    matches: list[dict], n_simulations: int, model_type: str
) -> tuple[pd.DataFrame, dict]:
    return run_monte_carlo_simulation(matches, n_simulations, model_type=model_type)


@st.cache_data(show_spinner=False)
def _cached_monte_carlo_history(
    matches: list[dict], n_simulations: int, model_type: str
) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    return calculate_monte_carlo_history(
        matches,
        n_simulations=n_simulations,
        model_type=model_type,
    )


@st.cache_data(show_spinner=False)
def _cached_next_match_impact(
    matches: list[dict], n_simulations: int, model_type: str
) -> tuple[dict[str, Any] | None, pd.DataFrame]:
    return calculate_next_match_impact(
        matches,
        n_simulations=n_simulations,
        model_type=model_type,
    )


def _default_relevant_positions(
    summary: pd.DataFrame, available_positions: list[str]
) -> list[str]:
    """Kies standaard 3 à 4 posities die direct aansluiten op ESHG's Monte Carlo-bereik."""
    n_pos = len(available_positions)
    if n_pos == 0:
        return []

    eshg_rows = summary.loc[summary["Team"] == _ESHG_TEAM]
    if eshg_rows.empty:
        return [p for p in ("Plek 4", "Plek 6", "Plek 8") if p in available_positions]

    row = eshg_rows.iloc[0]
    p10_pos = max(1, min(n_pos, int(round(float(row["10e Percentiel"])))))
    p90_pos = max(1, min(n_pos, int(round(float(row["90e Percentiel"])))))
    mean_pos = max(1, min(n_pos, int(round(float(row["Gemiddelde Eindpositie"])))))

    # Neem ambitieuze bovengrens (1 plek boven 10e percentiel) t/m ondergrens, max 4 lijnen
    low_pos = max(1, min(p10_pos - 1, mean_pos - 1))
    high_pos = min(n_pos, max(p90_pos, mean_pos + 1))

    chosen_nums = list(range(low_pos, high_pos + 1))
    if len(chosen_nums) > 4:
        # Houd bovengrens, midden (of Plek 6) en ondergrens over
        candidates = {low_pos, mean_pos, high_pos}
        if low_pos <= 6 <= high_pos:
            candidates.add(6)
        chosen_nums = sorted(candidates)[:4]
    elif len(chosen_nums) < 3:
        while len(chosen_nums) < min(3, n_pos):
            if chosen_nums[-1] < n_pos:
                chosen_nums.append(chosen_nums[-1] + 1)
            elif chosen_nums[0] > 1:
                chosen_nums.insert(0, chosen_nums[0] - 1)
            else:
                break

    return [f"Plek {num}" for num in chosen_nums if f"Plek {num}" in available_positions]


def _render_projected_points_fan_chart(
    summary: pd.DataFrame, distribution: dict[str, Any]
) -> None:
    trajectory = distribution.get("punten_verloop")
    if not isinstance(trajectory, pd.DataFrame) or trajectory.empty:
        return

    eshg_traj = trajectory[trajectory["Team"] == _ESHG_TEAM].sort_values("Ronde")
    if eshg_traj.empty:
        return

    st.subheader(f"📈 Verwacht puntenverloop t/m seizoenseinde · {_ESHG_TEAM}")

    max_played_round = int(distribution.get("max_played_round", 0))
    max_round = int(distribution.get("max_round", int(eshg_traj["Ronde"].max())))
    thresholds_df = distribution.get("positie_grenzen")

    available_positions: list[str] = []
    if isinstance(thresholds_df, pd.DataFrame) and not thresholds_df.empty:
        available_positions = [
            col for col in thresholds_df.columns if col.startswith("Plek ")
        ]

    default_positions = _default_relevant_positions(summary, available_positions)
    selected_positions_raw = st.multiselect(
        "Positiegrenzen per ronde in grafiek",
        options=available_positions,
        default=default_positions,
        format_func=lambda p: f"{p}{_THRESHOLD_SUFFIXES.get(p, '')}",
        key="mc_trajectory_position_lines",
        help="Standaard geselecteerd op basis van het verwachte speelveld van Don Quishoot H3.",
    )
    selected_set = set(selected_positions_raw)
    selected_positions = [p for p in available_positions if p in selected_set]

    actual_df = eshg_traj[eshg_traj["Ronde"] <= max_played_round]
    future_df = eshg_traj[eshg_traj["Ronde"] >= max_played_round]

    fig = go.Figure()

    # 80%-onzekerheidsband (P10 - P90) voor de resterende speelrondes
    if len(future_df) > 1:
        fig.add_trace(
            go.Scatter(
                x=future_df["Ronde"],
                y=future_df["P90"],
                mode="lines",
                line={"width": 0},
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=future_df["Ronde"],
                y=future_df["P10"],
                mode="lines",
                line={"width": 0},
                fill="tonexty",
                fillcolor="rgba(46, 125, 50, 0.16)",
                name="80% bandbreedte ESHG (P10–P90)",
                hoverinfo="skip",
            )
        )

    # Geselecteerde positiedrempels per ronde
    y_upper_candidates = [float(eshg_traj["P90"].max())]
    if (
        selected_positions
        and isinstance(thresholds_df, pd.DataFrame)
        and not thresholds_df.empty
    ):
        t_sorted = thresholds_df.sort_values("Ronde")
        for pos_label in selected_positions:
            y_upper_candidates.append(float(t_sorted[pos_label].max()))
            display_label = f"{pos_label}{_THRESHOLD_SUFFIXES.get(pos_label, '')}"
            color = _THRESHOLD_COLORS.get(pos_label, "#64748B")
            fig.add_trace(
                go.Scatter(
                    x=t_sorted["Ronde"],
                    y=t_sorted[pos_label],
                    mode="lines",
                    name=display_label,
                    line={"color": color, "width": 1.8, "dash": "dot"},
                    opacity=0.88,
                    hovertemplate=f"<b>{display_label}</b>: %{{y:.1f}} pt<extra></extra>",
                )
            )

    # Werkelijk behaalde punten tot nu toe
    if not actual_df.empty:
        fig.add_trace(
            go.Scatter(
                x=actual_df["Ronde"],
                y=actual_df["Verwachte_Punten"],
                mode="lines+markers",
                name=f"{_ESHG_TEAM} (werkelijk)",
                line={"color": _ESHG_COLOR, "width": 3.5},
                marker={"size": 7, "color": _ESHG_COLOR},
                hovertemplate=(
                    f"<b>{_ESHG_TEAM}</b>: <b>%{{y:.0f}} pt</b> (behaald)<extra></extra>"
                ),
            )
        )

    # Verwachte puntengroei vanaf huidige ronde
    if len(future_df) > 1:
        custom_band = list(zip(future_df["P10"], future_df["P90"]))
        fig.add_trace(
            go.Scatter(
                x=future_df["Ronde"],
                y=future_df["Verwachte_Punten"],
                mode="lines+markers",
                name=f"{_ESHG_TEAM} (verwacht)",
                customdata=custom_band,
                line={"color": _ESHG_COLOR, "width": 3, "dash": "dash"},
                marker={"size": 5, "color": _ESHG_COLOR},
                hovertemplate=(
                    f"<b>{_ESHG_TEAM} (verwacht)</b>: <b>%{{y:.1f}} pt</b> "
                    "(80%-band: %{customdata[0]:.0f}–%{customdata[1]:.0f} pt)<extra></extra>"
                ),
            )
        )

    if max_played_round > 0:
        fig.add_vline(
            x=max_played_round,
            line_dash="dot",
            line_color="rgba(128, 128, 128, 0.45)",
            annotation_text="Nu",
            annotation_position="top",
        )

    y_max = max(y_upper_candidates) if y_upper_candidates else 40.0
    fig.update_layout(
        height=440,
        margin={"l": 10, "r": 20, "t": 20, "b": 15},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        hoverlabel={
            "bgcolor": "rgba(24, 24, 27, 0.92)",
            "bordercolor": "rgba(255, 255, 255, 0.15)",
            "font": {"color": "#F4F4F5", "size": 12},
        },
        xaxis={
            "title": "Speelronde",
            "range": [-0.2, max_round + 0.5],
            "dtick": 1,
            "showgrid": False,
            "hoverformat": "d",
        },
        yaxis={
            "title": "Cumulatieve punten",
            "range": [0, max(y_max + 3, 6)],
            "dtick": 6,
            "showgrid": True,
            "gridcolor": "rgba(128, 128, 128, 0.18)",
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
    )

    st.caption(
        "Doorgetrokken groene lijn = behaalde punten · Gestippelde groene lijn + schaduwzone = "
        "verwachte punten en 80%-interval (10e–90e percentiel). "
        "De stippellijnen tonen het verwachte puntenaantal dat in die speelronde bij die positie hoort."
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _render_next_match_impact(
    matches: list[dict], n_simulations: int, model_type: str
) -> None:
    meta, impact_df = _cached_next_match_impact(matches, n_simulations, model_type)
    if meta is None or impact_df.empty:
        return

    st.subheader(
        f"⚡ Impact eerstvolgende wedstrijd · Ronde {meta['ronde']} vs. {meta['tegenstander']} ({meta['locatie']})"
    )
    st.caption(
        f"Wat gebeurt er met de eindkansen van {_ESHG_TEAM} na het duel op {meta['datum']} "
        f"bij winst, gelijkspel of verlies ({n_simulations:,} simulaties)?"
    )

    styled_impact = (
        impact_df.style.format(
            {
                "Verw. Positie": "{:.2f}",
                "Verw. Punten": "{:.1f}",
                "Kampioenschap (%)": "{:.1f}%",
                "Top 3 (%)": "{:.1f}%",
                "Linkerrijtje (%)": "{:.1f}%",
                "Degradatiekans (%)": "{:.1f}%",
            }
        ).background_gradient(
            subset=pd.Index(["Kampioenschap (%)", "Top 3 (%)", "Linkerrijtje (%)"]),
            cmap="RdYlGn",
        )
    )
    st.dataframe(
        styled_impact,
        hide_index=True,
        width="stretch",
    )


def _render_round_by_round_probabilities(
    matches: list[dict], n_simulations: int, model_type: str
) -> None:
    history_df, snapshots = _cached_monte_carlo_history(
        matches, n_simulations, model_type
    )
    if history_df.empty:
        return

    st.subheader(f"📊 Kansverloop per gespeelde ronde · {_ESHG_TEAM}")
    st.caption(
        f"Laat zien hoe de voorspelde eindkansen van Don Quishoot H3 na elke gespeelde "
        f"speelronde zijn verschoven ({n_simulations:,} simulaties per ronde)."
    )

    fig = go.Figure()
    series = [
        ("Linkerrijtje (%)", "#2E7D32", 3.0),
        ("Top 3 (%)", "#2563EB", 2.5),
        ("Kampioenschap (%)", "#D97706", 2.0),
        ("Degradatiekans (%)", "#DC2626", 2.0),
    ]
    for col_name, color, width in series:
        fig.add_trace(
            go.Scatter(
                x=history_df["Ronde"],
                y=history_df[col_name],
                mode="lines+markers",
                name=col_name.replace(" (%)", ""),
                line={"color": color, "width": width},
                marker={"size": 6, "color": color},
                hovertemplate=f"<b>{col_name.replace(' (%)', '')}</b>: %{{y:.1f}}%<extra></extra>",
            )
        )

    fig.update_layout(
        height=370,
        margin={"l": 10, "r": 20, "t": 15, "b": 15},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        hoverlabel={
            "bgcolor": "rgba(24, 24, 27, 0.92)",
            "bordercolor": "rgba(255, 255, 255, 0.15)",
            "font": {"color": "#F4F4F5", "size": 12},
        },
        xaxis={
            "title": "Na gespeelde speelronde",
            "dtick": 1,
            "showgrid": False,
            "hoverformat": "d",
        },
        yaxis={
            "title": "Kans (%)",
            "range": [0, 105],
            "dtick": 20,
            "ticksuffix": "%",
            "showgrid": True,
            "gridcolor": "rgba(128, 128, 128, 0.18)",
        },
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
        },
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    available_rounds = sorted(snapshots.keys(), reverse=True)
    if available_rounds:
        with st.expander("🔍 Bekijk volledige Monte Carlo-prognose na een eerdere speelronde", expanded=False):
            chosen_round = st.selectbox(
                "Selecteer gespeelde speelronde",
                options=available_rounds,
                index=0,
                format_func=lambda r: f"Na speelronde {r}",
                key="mc_historical_round_select",
            )
            snap_df = snapshots[chosen_round][
                [
                    "Team",
                    "Gemiddelde Eindpositie",
                    "Verwachte Punten",
                    "Kampioenschap (%)",
                    "Top 3 (%)",
                    "Linkerrijtje (%)",
                    "Degradatiekans (%)",
                ]
            ].rename(columns={"Gemiddelde Eindpositie": "MC Positie"})

            styled_snap = (
                snap_df.style.format(
                    {
                        "MC Positie": "{:.2f}",
                        "Verwachte Punten": "{:.1f}",
                        **{c: "{:.1f}%" for c in _PERCENT_COLUMNS},
                    }
                ).background_gradient(
                    subset=pd.Index(_PERCENT_COLUMNS), cmap="RdYlGn"
                )
            )
            st.dataframe(
                styled_snap,
                hide_index=True,
                width="stretch",
                height=(len(snap_df) + 1) * 36,
            )


def _render_monte_carlo(matches: list[dict]) -> None:
    col1, col2 = st.columns([2, 1])

    with col1:
        n_simulations = st.select_slider(
            "Aantal simulaties",
            options=[10, 100, 1000, 10000, 100000],
            value=1000,
            key="monte_carlo_simulation_count",
        )

    with col2:
        model_choice = st.radio(
            "Voorspelmodel",
            options=["Standaard", "Aangepast (Shrinkage + ELO)"],
            index=1,
            help="Standaard gebruikt pure doelpuntgemiddelden. Aangepast corrigeert kleine steekproeven richting het competitiegemiddelde en weegt ELO-verschil mee.",
        )
        model_type = "aangepast" if "Aangepast" in model_choice else "standaard"

    try:
        with st.spinner(f"Monte Carlo-simulaties uitvoeren ({n_simulations:,} runs)..."):
            summary, distribution = _cached_monte_carlo(
                matches, int(n_simulations), model_type
            )
    except ValueError as error:
        st.error(f"De seizoensprognose kon niet worden berekend: {error}")
        return

    if not isinstance(summary, pd.DataFrame):
        st.error("De simulatie heeft geen geldig prognoseresultaat opgeleverd.")
        return

    target_rows = summary.loc[summary["Team"] == _ESHG_TEAM]
    if target_rows.empty:
        st.info(f"{_ESHG_TEAM} is niet gevonden in het wedstrijdprogramma.")
    else:
        target = target_rows.iloc[0]
        kpi_columns = st.columns(4)
        kpi_columns[0].metric(
            "Verwachte Eindpositie",
            f"{target['Gemiddelde Eindpositie']:.2f}",
            f"Mediaan: {target['Mediaan']:.0f}",
        )
        kpi_columns[1].metric(
            "Kans op Kampioenschap",
            f"{target['Kampioenschap (%)']:.1f}%",
        )
        kpi_columns[2].metric("Kans op Top 3", f"{target['Top 3 (%)']:.1f}%")
        kpi_columns[3].metric(
            "Kans op Degradatiezone",
            f"{target['Degradatiekans (%)']:.1f}%",
        )

    st.subheader("Promotie / degradatie kansen")
    if summary.empty:
        st.info("Er zijn geen teams om te tonen.")
    else:
        current_standings = calculate_standings(matches)
        current_positions = {
            str(row["Team"]): int(row["Pos"])
            for _, row in current_standings.iterrows()
        }
        base_summary = summary.drop(columns=_PERCENT_POSITION).copy()
        base_summary = base_summary.rename(
            columns={
                "Gemiddelde Eindpositie": "MC"
            }
        )
        base_summary.insert(
            1,
            "KNHB",
            base_summary["Team"].map(current_positions).fillna(pd.NA).astype("Int64"),
        )
        base_summary.insert(
            3,
            "KNHB - MC",
            base_summary.apply(
                lambda row: (
                    float(row["KNHB"]) - float(row["MC"])
                    if pd.notna(row["KNHB"])
                    else pd.NA
                ),
                axis=1,
            ),
        )
        comparison_columns = [
            "Team",
            "KNHB",
            "MC",
            "KNHB - MC",
        ]
        remaining_columns = [
            column for column in base_summary.columns if column not in comparison_columns
        ]
        base_summary = base_summary[comparison_columns + remaining_columns]

        def style_monte_carlo_difference(row: pd.Series) -> list[str]:
            styles = [""] * len(row)
            difference = row["KNHB - MC"]
            if pd.notna(difference):
                for index, column in enumerate(row.index):
                    if column == "KNHB - MC":
                        styles[index] = _subtle_difference_color(float(difference))
                        break
            return styles

        styled_summary = (
            base_summary.style.format(
                {
                    **{column: "{:.1f}%" for column in _PERCENT_COLUMNS},
                    "MC": "{:.2f}",
                    "KNHB - MC": "{:+.2f}",
                    "Mediaan": "{:.0f}",
                    "10e Percentiel": "{:.0f}",
                    "90e Percentiel": "{:.0f}",
                    "Verwachte Punten": "{:.1f}",
                }
            )
            .background_gradient(
                subset=pd.Index(_PERCENT_COLUMNS), cmap="RdYlGn"
            )
            .apply(style_monte_carlo_difference, axis=1)
        )
        st.caption(
            "MC is de verwachte gemiddelde eindpositie. Het verschil "
            "is KNHB-stand minus Monte Carlo-stand; een negatieve waarde betekent "
            "dat KNHB het team hoger (dus beter) plaatst. De 10e en 90e Percentielen "
            "geven een 80%-interval van de gesimuleerde eindposities."
        )
        st.dataframe(
            styled_summary,
            hide_index=True,
            width="stretch",
            height=(len(summary) + 1) * 36,
            column_order=list(base_summary.columns),
            column_config={
                "Team": st.column_config.TextColumn("Team", width=120),
                "KNHB": st.column_config.NumberColumn(
                    "KNHB", width="small"
                ),
                "MC": st.column_config.NumberColumn(
                    "MC", width="small"
                ),
                "KNHB - MC": st.column_config.NumberColumn(
                    "KNHB - MC", width="small"
                ),
                **{
                    column: st.column_config.NumberColumn(column, width=120)
                    for column in _PERCENT_COLUMNS
                },
                "Mediaan": st.column_config.NumberColumn(
                    "Mediaan", width="small"
                ),
                "10e Percentiel": st.column_config.NumberColumn(
                    "10e Percentiel", width=80
                ),
                "90e Percentiel": st.column_config.NumberColumn(
                    "90e Percentiel", width=80
                ),
                "Verwachte Punten": st.column_config.NumberColumn(
                    "Verwachte Punten", width=100
                ),
            },
        )

    st.subheader("Verwachte eindstand")
    if summary.empty:
        st.info("Er zijn geen teams om te tonen.")
    else:
        positions_summary = summary[["Team"] + _PERCENT_POSITION]
        styled_summary_positions = (
            positions_summary.style.format(
                {
                    **{column: "{:.1f}%" for column in _PERCENT_POSITION},
                }
            )
            .background_gradient(
                subset=pd.Index(_PERCENT_POSITION), cmap="RdYlGn", axis=1
            )
        )
        st.dataframe(
            styled_summary_positions,
            hide_index=True,
            width="stretch",
            height=(len(summary) + 1) * 36,
        )

    position_distribution = distribution.get("positie_distributie")
    if isinstance(position_distribution, pd.DataFrame) and not position_distribution.empty:
        st.subheader(f"Kansverdeling eindpositie · {_ESHG_TEAM}")
        chart = px.bar(
            position_distribution,
            x="Positie",
            y="Kans (%)",
            text_auto=True,
            category_orders={
                "Positie": sorted(position_distribution["Positie"].tolist())
            },
            labels={"Positie": "Plek", "Kans (%)": "Kans %"},
            color_discrete_sequence=[_ESHG_COLOR],
        )
        chart.update_traces(texttemplate="%{y:.1f}%")
        chart.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin={"l": 10, "r": 10, "t": 15, "b": 10},
        )
        chart.update_xaxes(
            tickmode="array",
            tickvals=position_distribution["Positie"].tolist(),
            ticktext=[
                f"Plek {position}"
                for position in position_distribution["Positie"].tolist()
            ],
        )
        chart.update_yaxes(ticksuffix="%")
        st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})
    elif target_rows.empty:
        st.info(f"Er is geen eindpositieverdeling beschikbaar voor {_ESHG_TEAM}.")

    _render_projected_points_fan_chart(summary, distribution)
    with st.spinner("Overige analyses bijwerken..."):
        _render_next_match_impact(matches, int(n_simulations), model_type)
        _render_round_by_round_probabilities(matches, int(n_simulations), model_type)


def _render_power_rankings(matches: list[dict]) -> None:
    rankings = calculate_elo_ratings(matches)
    if rankings.empty:
        st.info("Er zijn nog geen teams in het wedstrijdprogramma.")
        return

    rankings = rankings.sort_values(
        "ELO Rating", ascending=False, kind="stable"
    ).reset_index(drop=True)
    rankings.insert(0, "ELO Positie", range(1, len(rankings) + 1))
    rankings["Verschil ELO vs. KNHB"] = (
        rankings["Positie KNHB"] - rankings["ELO Positie"]
    )
    elo_differences = {
        str(row["Team"]): float(row["Verschil ELO vs. KNHB"])
        for _, row in rankings.iterrows()
    }
    rankings["Positie KNHB"] = rankings.apply(
        lambda row: f"{int(row['Positie KNHB'])} ({row['Verschil ELO vs. KNHB']:+.0f})",
        axis=1,
    )
    rankings = rankings.drop(columns=["Verschil ELO vs. KNHB"])
    display_rankings = rankings.rename(
        columns={
            "SoS Gespeeld": "Moeilijkste programma tot nu toe",
            "SoS Resterend": "Zwaarste resterende programma",
        }
    )
    st.caption(
        "Een positieve afwijking betekent dat ELO het team hoger inschat dan de "
        "officiële KNHB-stand. Strength of Schedule is de gemiddelde ELO-rating "
        "van de tegenstanders; een hogere waarde duidt op sterkere tegenstand. "
        "Het getal tussen haakjes achter de KNHB-positie is het verschil "
        "tussen de KNHB- en ELO-positie."
    )

    def style_elo_difference(row: pd.Series) -> list[str]:
        difference_color = _subtle_difference_color(
            elo_differences[str(row["Team"])]
        )
        return [
            difference_color if column == "Positie KNHB" else ""
            for column in row.index
        ]

    st.dataframe(
        display_rankings.style.format(
            {
                "ELO Rating": "{:.1f}",
                "ELO Verschil t.o.v. Start": "{:+.1f}",
                "Moeilijkste programma tot nu toe": "{:.1f}",
                "Zwaarste resterende programma": "{:.1f}",
            }
        ).apply(style_elo_difference, axis=1),
        hide_index=True,
        width="stretch",
        height=(len(display_rankings) + 1) * 36,
        column_config={
            "ELO Positie": st.column_config.NumberColumn("ELO Positie", width="small"),
            "Positie KNHB": st.column_config.TextColumn("Positie KNHB", width="small"),
            "Team": st.column_config.TextColumn("Team", width="medium"),
            "ELO Rating": st.column_config.NumberColumn("ELO Rating", width="small"),
            "ELO Verschil t.o.v. Start": st.column_config.NumberColumn(
                "ELO Verschil t.o.v. Start", width="small"
            ),
            "Moeilijkste programma tot nu toe": st.column_config.NumberColumn(
                "Moeilijkste programma tot nu toe", width="small"
            ),
            "Zwaarste resterende programma": st.column_config.NumberColumn(
                "Zwaarste resterende programma", width="small"
            ),
        },
    )


def render_simulation_view() -> None:
    st.title("🎲 Simulaties & ELO")
    try:
        matches = get_all_matches()
    except ValueError as error:
        st.error(f"Het wedstrijdprogramma kon niet worden geladen: {error}")
        return

    forecast_tab, rankings_tab = st.tabs(
        ["🏆 Monte Carlo Seizoensprognose", "⚡ Poule Power Rankings & ELO"]
    )
    with forecast_tab:
        _render_monte_carlo(matches)
    with rankings_tab:
        _render_power_rankings(matches)