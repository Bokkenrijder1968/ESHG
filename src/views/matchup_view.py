import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote

import pandas as pd
import plotly.graph_objects as go
import streamlit as st  # type: ignore[import-not-found]

from src.calculations import (
    get_all_matches,
    get_common_opponents_comparison,
    get_head_to_head,
    get_opponent_form,
    get_opponents_by_schedule,
    predict_match_outcome,
)
from src.constants import OPPONENTS, REISTIJDEN_MINUTEN


_ESHG_TEAM = "Don Quishoot H3"
_RESULT_COLORS = {"W": "#198754", "G": "#6c757d", "V": "#dc3545"}

_MODEL_OPTIONS = {
    "ELO + Aanval/Verdediging (Aanbevolen)": "elo",
    "Gecombineerd Ensemble": "ensemble",
    "Recente Vorm (Laatste 3)": "recent",
    "Gedeelde Tegenstanders": "gedeeld",
    "Seizoensgemiddelde": "seizoen",
}


def _render_match_location(
    matches: list[dict[str, Any]], opponent: str
) -> None:
    """Rendert de locatie en verzameltijd voor een komende wedstrijd."""
    upcoming_matches = sorted(
        (
            match
            for match in matches
            if match.get("gespeeld") is False
            and _ESHG_TEAM in (match.get("thuis"), match.get("uit"))
            and opponent in (match.get("thuis"), match.get("uit"))
        ),
        key=lambda match: str(match.get("datum", "")),
    )

    st.subheader("📍 Locatie & Verzameltijd")

    if not upcoming_matches:
        st.info(f"Er is geen komende wedstrijd tegen {opponent} bekend.")
        return

    komende_wedstrijd = upcoming_matches[0]
    wedstrijd_tijd = komende_wedstrijd.get("tijd") or komende_wedstrijd.get("aanvang")
    accommodatie = komende_wedstrijd.get(
        "locatie_accommodatie", "Accommodatie onbekend"
    )
    adres = komende_wedstrijd.get("locatie_adres", "")
    veld_naam = komende_wedstrijd.get("veld_naam", "Veld onbekend")
    veld_type = komende_wedstrijd.get("veld_type", "Onbekend type")
    is_thuis = komende_wedstrijd.get("thuis") == _ESHG_TEAM

    if is_thuis:
        col1, col2, col3 = st.columns(3)
        col1.metric("Type wedstrijd", "Thuis (Eindhoven)")
        col2.metric("Aanvang", wedstrijd_tijd if wedstrijd_tijd else "Tijd volgt")

        if wedstrijd_tijd:
            aanwezig, _ = bereken_tijdschema(wedstrijd_tijd, reistijd_minuten=0, buffer_minuten=0)
            col3.metric("Aanwezig op TU/e (-45m)", aanwezig)
        else:
            col3.metric("Aanwezig op TU/e", "Tijd volgt")

        st.caption(f"**Veld:** {veld_naam} ({veld_type}) | **Locatie:** {accommodatie}")
    else:
        key = normalize_key(opponent)
        reistijd = REISTIJDEN_MINUTEN.get(key, 35)

        if wedstrijd_tijd:
            aanwezig, verzamelen = bereken_tijdschema(
                wedstrijd_tijd, reistijd_minuten=reistijd, buffer_minuten=5
            )
        else:
            aanwezig, verzamelen = None, None

        col1, col2, col3 = st.columns(3)
        col1.metric("🚗 Reistijd auto", f"~{reistijd} min")
        col2.metric("🏟️ Aanwezig bij club (-45m)", aanwezig if aanwezig else "Tijd volgt")
        col3.metric("📍 Verzamelen Nassaustraat", verzamelen if verzamelen else "Tijd volgt")

        st.caption(
            f"**Veld:** {veld_naam} ({veld_type}) | "
            f"**Accommodatie:** {accommodatie} | "
            f"*(Inclusief 5 min buffer tassen/instappen)*"
        )

    if adres:
        render_google_maps_embed(adres, hoogte=260)

        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={quote(adres)}"
        st.link_button("🗺️ Open in Google Maps Navigatie", google_maps_url, width="stretch")
    else:
        st.info("Locatieadres nog niet bekend voor deze wedstrijd.")


def normalize_key(name: str) -> str:
    """Maakt van bijv. 'Warande H3' -> 'warandeh3' voor lookup."""
    return re.sub(r"[\s\-_]+", "", name or "").lower()


def bereken_tijdschema(wedstrijd_tijd_str: str, reistijd_minuten: int, buffer_minuten: int = 5):
    """Berekent aanwezigheid (T - 45 min) en verzameltijd (Aanwezig - reistijd - buffer)."""
    if not wedstrijd_tijd_str:
        return None, None
    try:
        start_dt = datetime.strptime(wedstrijd_tijd_str, "%H:%M")
        aanwezig_dt = start_dt - timedelta(minutes=45)
        verzamelen_dt = aanwezig_dt - timedelta(minutes=reistijd_minuten + buffer_minuten)

        return aanwezig_dt.strftime("%H:%M"), verzamelen_dt.strftime("%H:%M")
    except ValueError:
        return None, None


def render_google_maps_embed(adres: str, hoogte: int = 300):
    """Toont een interactieve Google Maps kaart zonder API key."""
    if not adres:
        return
    encoded_addr = quote(adres)
    embed_url = f"https://maps.google.com/maps?q={encoded_addr}&t=&z=15&ie=UTF8&iwloc=&output=embed"

    st.iframe(
        f"""
        <iframe 
            width="100%"
            height="{hoogte}"
            frameborder="0"
            scrolling="no"
            marginheight="0"
            marginwidth="0"
            src="{embed_url}"
            style="border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.1);">
        </iframe>
        """,
        height=hoogte + 10,
    )


def _render_probability_bar(win_eshg: float, draw: float, win_opp: float, opponent: str) -> None:
    fig = go.Figure()
    segments = [
        (f"Winst {_ESHG_TEAM}", win_eshg * 100, "#2E7D32"),
        ("Gelijkspel", draw * 100, "#64748B"),
        (f"Winst {opponent}", win_opp * 100, "#DC2626"),
    ]
    for label, pct, color in segments:
        fig.add_trace(
            go.Bar(
                y=["Kans"],
                x=[pct],
                name=label,
                orientation="h",
                marker={"color": color},
                text=[f"{pct:.0f}%" if pct >= 8 else ""],
                textposition="inside",
                insidetextanchor="middle",
                textfont={"color": "white", "size": 13},
                hovertemplate=f"<b>{label}</b>: %{{x:.1f}}%<extra></extra>",
            )
        )

    fig.update_layout(
        barmode="stack",
        height=72,
        margin={"l": 0, "r": 0, "t": 6, "b": 6},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis={"range": [0, 100], "visible": False, "fixedrange": True},
        yaxis={"visible": False, "fixedrange": True},
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def _render_prediction(matches: list[dict[str, Any]], opponent: str) -> None:
    selected_label = st.radio(
        "Rekenmodel",
        list(_MODEL_OPTIONS.keys()),
        index=0,
        horizontal=True,
        key="matchup_prediction_model",
    )
    model_code = _MODEL_OPTIONS[selected_label]
    prediction = predict_match_outcome(matches, _ESHG_TEAM, opponent, model_type=model_code)

    if prediction is None:
        st.info("Er zijn nog onvoldoende gespeelde competitiewedstrijden voor een statistische voorspelling.")
        return

    win_eshg = float(prediction["win_a"])
    draw = float(prediction["draw"])
    win_opp = float(prediction["win_b"])

    c1, c2, c3 = st.columns(3)
    c1.metric(f"Winst {_ESHG_TEAM}", f"{win_eshg:.0%}")
    c2.metric("Gelijkspel", f"{draw:.0%}")
    c3.metric(f"Winst {opponent}", f"{win_opp:.0%}")

    _render_probability_bar(win_eshg, draw, win_opp, opponent)

    league_avg = float(prediction["league_avg"])
    prof_a = prediction["profile_a"]
    prof_b = prediction["profile_b"]

    st.markdown(f"**Teamprofiel t.o.v. poulegemiddelde ({league_avg:.1f} goals/wedstrijd)**")
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        with st.container(border=True):
            st.markdown(f"**{_ESHG_TEAM}** *({prof_a['gespeeld']} GS)*")
            st.markdown(
                f"⚽ **Aanval:** {prof_a['aanval_label']} — **{prof_a['voor_gem']:.1f}** voor/wedstrijd"
            )
            st.markdown(
                f"🛡️ **Verdediging:** {prof_a['verdediging_label']} — **{prof_a['tegen_gem']:.1f}** tegen/wedstrijd"
            )
    with p_col2:
        with st.container(border=True):
            st.markdown(f"**{opponent}** *({prof_b['gespeeld']} GS)*")
            st.markdown(
                f"⚽ **Aanval:** {prof_b['aanval_label']} — **{prof_b['voor_gem']:.1f}** voor/wedstrijd"
            )
            st.markdown(
                f"🛡️ **Verdediging:** {prof_b['verdediging_label']} — **{prof_b['tegen_gem']:.1f}** tegen/wedstrijd"
            )

    st.caption(
        f"Spelbeeld: **{prediction['tempo_label']}** "
        f"(verwachte doelpunten: ESHG {prediction['lambda_a']:.1f} – {opponent} {prediction['lambda_b']:.1f})."
    )

    with st.expander("Onderliggende modeldetails & waarschijnlijkste uitslagen", expanded=False):
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("**ELO-krachtsverhouding**")
            st.write(
                f"- **{_ESHG_TEAM}:** {prediction['elo_a']:.0f}\n"
                f"- **{opponent}:** {prediction['elo_b']:.0f}\n"
                f"- **Verschil:** {prediction['elo_diff']:+.0f} ELO"
            )
        with d2:
            st.markdown("**Top 3 meest waarschijnlijke uitslagen (Poisson)**")
            for item in prediction["top_scores"]:
                st.write(f"- **{item['score']}** ({item['kans']:.1%} kans)")


def _format_h2h_cards(raw_cards: object) -> str:
    if isinstance(raw_cards, str):
        return raw_cards.strip()
    if isinstance(raw_cards, list):
        formatted = []
        for item in raw_cards:
            if isinstance(item, dict):
                speler = str(item.get("speler", "")).strip()
                k_type = str(item.get("type", "")).strip()
                if speler and k_type:
                    formatted.append(f"{speler} ({k_type})")
        return ", ".join(formatted)
    return ""


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
            cards = _format_h2h_cards(extra_stats.get("kaarten"))
            substitutes = str(extra_stats.get("invallers", "")).strip()
            saved_notes = [
                f"**Speelstijl (press / zone / corners):** {tactics}" if tactics else "",
                f"**Leerpunten:** {evaluation}" if evaluation else "",
                f"**Kaarten:** {cards}" if cards else "",
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

    _render_match_location(matches, opponent)