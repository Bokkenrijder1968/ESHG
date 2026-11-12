import pandas as pd
import plotly.express as px
import streamlit as st # type: ignore[import-not-found]

from src.calculations import (
    calculate_elo_ratings,
    calculate_standings,
    get_all_matches,
    run_monte_carlo_simulation,
)


_ESHG_TEAM = "Don Quishoot H3"
_PERCENT_COLUMNS = [
    "Kampioenschap (%)",
    "Top 3 (%)",
    "Degradatiekans (%)",
    "Linkerrijtje (%)",
]

_PERCENT_POSITION=[
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


def _render_monte_carlo(matches: list[dict]) -> None:
    # Knoppen/sliders netjes naast elkaar in 2 kolommen
    col1, col2 = st.columns([2, 1])

    with col1:
        n_simulations = st.select_slider(
            "Aantal simulaties",
            options=[10, 500, 1000, 2500, 10000],
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

    if st.button("Start Simulatie", type="primary"):
        try:
            st.session_state["monte_carlo_result"] = _cached_monte_carlo(
                matches, n_simulations, model_type
            )
        except ValueError as error:
            st.error(f"De seizoensprognose kon niet worden berekend: {error}")
            return
        

    result = st.session_state.get("monte_carlo_result")
    if not isinstance(result, tuple) or len(result) != 2:
        st.info("Start de simulatie om de seizoensprognose te bekijken.")
        return
    summary, distribution = result
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
            "dat KNHB het team hoger (dus beter) plaatst. De 10e en 90e Percentielentielen "
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
        st.dataframe(styled_summary_positions, hide_index=True, width="stretch", height=(len(summary)+1) * 36)

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
            color_discrete_sequence=["#2e8b57"],
        )
        chart.update_traces(texttemplate="%{y:.1f}%")
        chart.update_xaxes(
            tickmode="array",
            tickvals=position_distribution["Positie"].tolist(),
            ticktext=[
                f"Plek {position}"
                for position in position_distribution["Positie"].tolist()
            ],
        )
        chart.update_yaxes(ticksuffix="%")
        st.plotly_chart(chart, width="stretch")
    elif target_rows.empty:
        st.info(f"Er is geen eindpositieverdeling beschikbaar voor {_ESHG_TEAM}.")


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
