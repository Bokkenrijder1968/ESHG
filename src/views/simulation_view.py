import pandas as pd
import plotly.express as px
import streamlit as st

from src.calculations import (
    calculate_elo_ratings,
    get_all_matches,
    run_monte_carlo_simulation,
)


_ESHG_TEAM = "Don Quishoot H3"
_PERCENT_COLUMNS = [
    "Kans op Kampioenschap (%)",
    "Kans op Top 3 (%)",
    "Kans op Degradatiezone (%)",
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

@st.cache_data(show_spinner=False)
def _cached_monte_carlo(
    matches: list[dict], n_simulations: int
) -> tuple[pd.DataFrame, dict]:
    return run_monte_carlo_simulation(matches, n_simulations)


def _render_monte_carlo(matches: list[dict]) -> None:
    n_simulations = st.select_slider(
        "Aantal simulaties",
        options=[500, 600, 1000, 2500, 10000],
        value=1000,
        key="monte_carlo_simulation_count",
    )
    if st.button("Start Simulatie", type="primary"):
        try:
            st.session_state["monte_carlo_result"] = _cached_monte_carlo(
                matches, n_simulations
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
            f"{target['Verwachte Eindpositie (gemiddeld)']:.2f}",
            f"Mediaan: {target['Verwachte Eindpositie (mediaan)']:.0f}",
        )
        kpi_columns[1].metric(
            "Kans op Kampioenschap",
            f"{target['Kans op Kampioenschap (%)']:.1f}%",
        )
        kpi_columns[2].metric("Kans op Top 3", f"{target['Kans op Top 3 (%)']:.1f}%")
        kpi_columns[3].metric(
            "Kans op Degradatiezone",
            f"{target['Kans op Degradatiezone (%)']:.1f}%",
        )

    st.subheader("Promotie / degradatie kansen")
    if summary.empty:
        st.info("Er zijn geen teams om te tonen.")
    else:
        base_summary = summary.drop(columns=_PERCENT_POSITION)
        styled_summary = (
            base_summary.style.format(
                {
                    **{column: "{:.1f}%" for column in _PERCENT_COLUMNS},
                    "Verwachte Eindpositie (gemiddeld)": "{:.2f}",
                    "Verwachte Eindpositie (mediaan)": "{:.1f}",
                    "Verwachte Punten (gemiddeld)": "{:.1f}",
                }
            )
            .background_gradient(
                subset=pd.Index(_PERCENT_COLUMNS), cmap="RdYlGn"
            )
        )
        st.dataframe(styled_summary, hide_index=True, width="stretch", height=(len(summary) + 1) * 36)

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
    display_rankings = rankings.rename(
        columns={
            "SoS Gespeeld": "Moeilijkste programma tot nu toe",
            "SoS Resterend": "Zwaarste resterende programma",
        }
    )
    st.caption(
        "Een positieve afwijking betekent dat ELO het team hoger inschat dan de "
        "officiële KNHB-stand. Strength of Schedule is de gemiddelde ELO-rating "
        "van de tegenstanders; een hogere waarde duidt op sterkere tegenstand."
    )
    st.dataframe(
        display_rankings.style.format(
            {
                "ELO Rating": "{:.1f}",
                "ELO Verschil t.o.v. Start": "{:+.1f}",
                "Moeilijkste programma tot nu toe": "{:.1f}",
                "Zwaarste resterende programma": "{:.1f}",
                "Verschil ELO vs. KNHB": "{:+.0f}",
            }
        ).background_gradient(
            subset=pd.Index(["Verschil ELO vs. KNHB"]), cmap="RdYlGn"
        ),
        hide_index=True,
        width="stretch",
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
