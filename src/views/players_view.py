import pandas as pd
import plotly.express as px
import streamlit as st
import numpy as np
np.random.seed(42)

from src.calculations import (
    calculate_player_stats,
    get_player_match_timeline,
    get_top_duos,
)
from src.constants import PLAYERS


def _render_podium_card(title: str, top_players: list[tuple[str, int]], unit: str) -> None:
    """Rendert een podiumkaart voor de top 3 van een categorie."""
    medals = ["🥇", "🥈", "🥉"]
    with st.container(border=True):
        st.markdown(f"#### {title}")
        for idx, (player, count) in enumerate(top_players[:3]):
            medal = medals[idx] if idx < len(medals) else f"{idx + 1}."
            st.markdown(
                f"<div style='display: flex; justify-content: space-between; align-items: center; "
                f"margin-bottom: 6px; padding: 4px 8px; background-color: rgba(255,255,255,0.04); "
                f"border-radius: 6px;'>"
                f"<span><strong style='font-size: 1.1em;'>{medal}</strong> {player}</span>"
                f"<span style='font-weight: 600; color: #4ade80;'>{count} {unit}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )


def render_players_view() -> None:
    st.title("🏑 Spelers & Stats")

    try:
        player_stats = calculate_player_stats()
    except Exception as error:
        st.error(f"Fout bij het laden van spelerstatistieken: {error}")
        return

    if player_stats.empty:
        st.info("Er zijn nog geen doelpunten- of assistgegevens beschikbaar.")
        return

    # =========================================================================
    # 1. PODIA (Top 3 voor Goals, Assists en Totaal G+A)
    # =========================================================================
    st.subheader("🏆 De Podia")
    
    top_goals = (
        player_stats[player_stats["Goals"] > 0]
        .sort_values(["Goals", "Veldgoals"], ascending=False)[["Speler", "Goals"]]
        .values.tolist()
    )
    top_assists = (
        player_stats[player_stats["Assists"] > 0]
        .sort_values("Assists", ascending=False)[["Speler", "Assists"]]
        .values.tolist()
    )
    top_mvp = (
        player_stats[player_stats["Totaal_G_A"] > 0]
        .sort_values(["Totaal_G_A", "Goals"], ascending=False)[["Speler", "Totaal_G_A"]]
        .values.tolist()
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        _render_podium_card("Topscorers", top_goals, "goals")
    with c2:
        _render_podium_card("Assistkoningen", top_assists, "assists")
    with c3:
        _render_podium_card("MVP (Goals + Assists)", top_mvp, "G+A")

    # =========================================================================
    # 2. CHECK: NOG OP DE NUL (Goals / Assists)
    # =========================================================================
    with st.expander("🎯 Wie staat er nog op nul?", expanded=True):
        zero_goals = player_stats[player_stats["Goals"] == 0]["Speler"].tolist()
        zero_assists = player_stats[player_stats["Assists"] == 0]["Speler"].tolist()
        zero_both = player_stats[(player_stats["Goals"] == 0) & (player_stats["Assists"] == 0)]["Speler"].tolist()

        z_col1, z_col2, z_col3 = st.columns(3)
        with z_col1:
            st.markdown(f"**Nog geen goal ({len(zero_goals)}):**")
            st.caption(", ".join(zero_goals) if zero_goals else "🎉 Iedereen heeft gescoord!")

        with z_col2:
            st.markdown(f"**Nog geen assist ({len(zero_assists)}):**")
            st.caption(", ".join(zero_assists) if zero_assists else "🎉 Iedereen heeft een assist!")

        with z_col3:
            st.markdown(f"**De dubbele nul ({len(zero_both)}):**")
            st.caption(", ".join(zero_both) if zero_both else "Niemand!")

    # =========================================================================
    # 3. VISUELE STAAFDIAGRAM (Actieve spelers, netjes gesorteerd van hoog naar laag)
    # =========================================================================
    active_players = player_stats[player_stats["Totaal_G_A"] > 0].copy()

    if not active_players.empty:
        st.subheader("📊 Productie per speler")

        active = player_stats[player_stats["Totaal_G_A"] > 0].copy()

        # 1. Groepeer op coördinaten en tel direct het exacte aantal spelers binnen de aggregatie
        grouped = (
            active.groupby(["Assists", "Goals", "Totaal_G_A"])
            .agg(
                Speler=("Speler", lambda names: " & ".join(sorted(names))),
                Aantal_Spelers=("Speler", "count"),
            )
            .reset_index()
        )

        # 2. Plotly scatter plot
        fig = px.scatter(
            grouped,
            x="Assists",
            y="Goals",
            text="Speler",
            color="Totaal_G_A",
            size="Aantal_Spelers",
            size_max=26,  # Maximale grootte voor de grootste groep (3 spelers)
            color_continuous_scale="Viridis",
            hover_data={
                "Speler": True,
                "Aantal_Spelers": True,
                "Goals": True,
                "Assists": True,
                "Totaal_G_A": True,
            },
        )

        # Kwadrantlijnen
        fig.add_hline(y=1.5, line_dash="dot", line_color="rgba(255,255,255,0.2)")
        fig.add_vline(x=1.5, line_dash="dot", line_color="rgba(255,255,255,0.2)")

        fig.update_traces(
            textposition="top center",
            marker=dict(
                sizemin=12,  # Voorkomt dat stippen met 1 speler te klein worden
                line=dict(width=1.5, color="white"),
            ),
        )

        fig.update_layout(
            height=440,
            xaxis=dict(
                title="Assists ➔",
                dtick=1,
                range=[-0.4, max(active["Assists"]) + 0.8],
            ),
            yaxis=dict(
                title="Goals ➔",
                dtick=1,
                range=[-0.4, max(active["Goals"]) + 0.8],
            ),
            showlegend=False,
            coloraxis_showscale=False,
            margin=dict(l=20, r=20, t=30, b=20),
        )

        st.plotly_chart(fig, use_container_width=True)

    # =========================================================================
    # 4. GOUDEN DUO'S
    # =========================================================================
    try:
        top_duos = get_top_duos()
        if not top_duos.empty:
            st.subheader("🤝 Gouden duo's")
            st.dataframe(top_duos, hide_index=True, use_container_width=True)
    except Exception:
        pass

    # =========================================================================
    # 5. VOLLEDIGE TABEL (Zonder kleuren + Klikbare rijen)
    # =========================================================================
    st.subheader("📋 Volledige spelersstatistieken")
    st.caption("💡 *Klik op een rij in de tabel om hieronder direct de wedstrijdstatistieken van die speler te zien.*")

    display_table = player_stats.rename(columns={"Totaal_G_A": "Totaal"})

    # Interactieve tabel zonder achtergrondkleuren
    table_event = st.dataframe(
        display_table,
        hide_index=True,
        width="stretch",
        height=(min(len(display_table), 15) + 1) * 36,
        on_select="rerun",
        selection_mode="single-row",
        key="players_overview_table",
    )

    # =========================================================================
    # 6. SPELERSDETAILS (Automatisch gekoppeld aan de gekozen rij)
    # =========================================================================
    selected_rows = (
        table_event.selection.rows
        if table_event and hasattr(table_event, "selection")
        else []
    )

    # Pak de aangeklikte speler; neem standaard de bovenste speler als er nog niets is aangeklikt
    if selected_rows:
        selected_player = display_table.iloc[selected_rows[0]]["Speler"]
    elif not display_table.empty:
        selected_player = display_table.iloc[0]["Speler"]
    else:
        selected_player = None

    if selected_player:
        st.subheader(f"🔍 Wedstrijddetails · {selected_player}")
        timeline = get_player_match_timeline(selected_player)

        if timeline.empty:
            st.info(f"{selected_player} heeft dit seizoen nog geen geregistreerde goals of assists.")
        else:
            st.dataframe(timeline, hide_index=True, width="stretch")