import streamlit as st  # type: ignore[import-not-found]

from src.constants import ENABLE_PITCHERS
from src.views.input_view import render_input_view
from src.views.matchup_view import render_matchup_view
from src.views.pitchers_view import render_pitchers_view
from src.views.players_view import render_players_view
from src.views.scenario_view import render_scenario_view
from src.views.simulation_view import render_simulation_view
from src.views.table_view import render_table_view
from src.views.trends_view import render_trends_view

st.set_page_config(page_title="ESHG H1", layout="wide", page_icon="🏑")

st.markdown("# ESHG H1 Manager 🏑")

tab_titles = [
    "📝 Wedstrijd Invoeren",
    "🏆 Stand & Schema",
    "🎯 Matchup & Analyse",
    "🔮 Scenario Calculator",
    "📊 Spelerstatistieken",
    "📈 Teamstatistieken",
    "🎲 Simulaties & ELO",
]
if ENABLE_PITCHERS:
    tab_titles.append("🍺 Pitchers")

tabs = st.tabs(tab_titles)

with tabs[0]:
    render_input_view()

with tabs[1]:
    render_table_view()

with tabs[2]:
    render_matchup_view()

with tabs[3]:
    render_scenario_view()

with tabs[4]:
    render_players_view()

with tabs[5]:
    render_trends_view()

with tabs[6]:
    render_simulation_view()

if ENABLE_PITCHERS:
    with tabs[7]:
        render_pitchers_view()