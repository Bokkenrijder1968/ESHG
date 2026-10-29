import streamlit as st
from src.views.input_view import render_input_view
from src.views.matchup_view import render_matchup_view
from src.views.scenario_view import render_scenario_view
from src.views.players_view import render_players_view
from src.views.simulation_view import render_simulation_view
from src.views.table_view import render_table_view
from src.views.trends_view import render_trends_view

st.set_page_config(page_title="Don Quishoot H3 Manager", layout="wide", page_icon="🏑")

tab_invoer, tab_stand, tab_matchup, tab_scenario, tab_stats, tab_trends, tab_simulaties = st.tabs(
    [
        "📝 Wedstrijd Invoeren",
        "🏆 Stand & Schema",
        "🎯 Matchup & Analyse",
        "🔮 Scenario Calculator",
        "📊 Spelers & Stats",
        "📈 Trends & Fysiek",
        "🎲 Simulaties & ELO",
    ]
)

with tab_invoer:
    render_input_view()

with tab_stand:
    render_table_view()

with tab_matchup:
    render_matchup_view()

with tab_scenario:
    render_scenario_view()

with tab_stats:
    render_players_view()

with tab_trends:
    render_trends_view()

with tab_simulaties:
    render_simulation_view()