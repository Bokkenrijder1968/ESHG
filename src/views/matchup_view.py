import math
from typing import Any

import pandas as pd
import streamlit as st

from datetime import datetime, timedelta
from urllib.parse import quote

from src.calculations import (
    _common_opponents_expected_diff,
    _team_recent_averages,
    _team_match_result,
    get_all_matches,
    get_common_opponents_comparison,
    get_head_to_head,
    get_opponents_by_schedule,
    get_opponent_form,
)
from src.constants import OPPONENTS, REISTIJDEN_MINUTEN


_ESHG_TEAM = "Don Quishoot H3"
_RESULT_COLORS = {"W": "#198754", "G": "#6c757d", "V": "#dc3545"}


def _team_averages(
    matches: list[dict[str, Any]], team: str
) -> tuple[float, float, int]:
    played = [
        result
        for match in matches
        if (result := _team_match_result(match, team)) is not None
    ]
    if not played:
        return 0.0, 0.0, 0

    return (
        sum(match["doelpunten_voor"] for match in played) / len(played),
        sum(match["doelpunten_tegen"] for match in played) / len(played),
        len(played),
    )


def _poisson_probabilities(expected_goals: float) -> list[float]:
    max_goals = min(
        100,
        max(12, math.ceil(expected_goals + 8 * math.sqrt(expected_goals + 1))),
    )
    probabilities = [math.exp(-expected_goals)]
    for goals in range(1, max_goals + 1):
        probabilities.append(
            probabilities[-1] * expected_goals / goals
        )
    return probabilities



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
        # Uitwedstrijd: haal vaste reistijd op
        key = normalize_key(opponent)
        reistijd = REISTIJDEN_MINUTEN.get(key, 35)  # 35 min fallback
        
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

    # Google Maps Kaart en navigatielink
    if adres:
        render_google_maps_embed(adres, hoogte=260)
        
        google_maps_url = f"https://www.google.com/maps/search/?api=1&query={quote(adres)}"
        st.link_button("🗺️ Open in Google Maps Navigatie", google_maps_url, width='stretch')
    else:
        st.info("Locatieadres nog niet bekend voor deze wedstrijd.")


def normalize_key(name: str) -> str:
    """Maakt van bijv. 'Warande H3' -> 'warandeh3' voor lookup."""
    import re
    return re.sub(r"[\s\-_]+", "", name or "").lower()

def bereken_tijdschema(wedstrijd_tijd_str: str, reistijd_minuten: int, buffer_minuten: int = 5):
    """
    Berekent aanwezigheid (T - 45 min) en verzameltijd (Aanwezig - reistijd - buffer).
    """
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


def _render_prediction(matches: list[dict[str, Any]], opponent: str) -> None:
    model = st.radio(
        "Rekenmodel",
        [
            "Seizoensgemiddelde (Standaard)",
            "Recente Vorm (Laatste 3 wedstrijden)",
            "Gedeelde Tegenstanders",
            "Gecombineerd Ensemble",
        ],
        horizontal=True,
        key="matchup_prediction_model",
    )
    eshg_scored, eshg_conceded, eshg_played = _team_averages(matches, _ESHG_TEAM)
    opponent_scored, opponent_conceded, opponent_played = _team_averages(
        matches, opponent
    )
    if not eshg_played or not opponent_played:
        st.info("Er zijn nog onvoldoende gespeelde wedstrijden voor een voorspelling.")
        return

    seasonal_expected_eshg = (eshg_scored + opponent_conceded) / 2
    seasonal_expected_opponent = (opponent_scored + eshg_conceded) / 2
    recent_eshg_scored, recent_eshg_conceded = _team_recent_averages(
        matches, _ESHG_TEAM
    )
    recent_opponent_scored, recent_opponent_conceded = _team_recent_averages(
        matches, opponent
    )
    recent_expected_eshg = (
        recent_eshg_scored + recent_opponent_conceded
    ) / 2
    recent_expected_opponent = (
        recent_opponent_scored + recent_eshg_conceded
    ) / 2
    relative_difference = _common_opponents_expected_diff(
        matches, _ESHG_TEAM, opponent
    )
    common_expected_eshg = max(0.0, 2.5 + relative_difference / 2)
    common_expected_opponent = max(0.0, 2.5 - relative_difference / 2)

    if model == "Recente Vorm (Laatste 3 wedstrijden)":
        expected_eshg = recent_expected_eshg
        expected_opponent = recent_expected_opponent
    elif model == "Gedeelde Tegenstanders":
        expected_eshg = common_expected_eshg
        expected_opponent = common_expected_opponent
    elif model == "Gecombineerd Ensemble":
        expected_eshg = (
            0.40 * common_expected_eshg
            + 0.35 * recent_expected_eshg
            + 0.25 * seasonal_expected_eshg
        )
        expected_opponent = (
            0.40 * common_expected_opponent
            + 0.35 * recent_expected_opponent
            + 0.25 * seasonal_expected_opponent
        )
    else:
        expected_eshg = seasonal_expected_eshg
        expected_opponent = seasonal_expected_opponent

    eshg_probabilities = _poisson_probabilities(expected_eshg)
    opponent_probabilities = _poisson_probabilities(expected_opponent)
    win_probability = sum(
        eshg_chance * sum(opponent_probabilities[:goals])
        for goals, eshg_chance in enumerate(eshg_probabilities)
    )
    draw_probability = sum(
        eshg_chance * opponent_probabilities[goals]
        for goals, eshg_chance in enumerate(eshg_probabilities)
        if goals < len(opponent_probabilities)
    )
    loss_probability = max(0.0, 1 - win_probability - draw_probability)
    st.metric(
        "Verwachte uitslag",
        f"{round(expected_eshg)} - {round(expected_opponent)}",
        help=(
            f"Doelpuntenverwachting: ESHG {expected_eshg:.1f} – "
            f"{opponent} {expected_opponent:.1f}"
        ),
    )
    st.caption(
        f"Indicatieve kansen · model: {model} (Poisson-verdeling): "
        f"ESHG winst {win_probability:.0%} · gelijk {draw_probability:.0%} · "
        f"{opponent} winst {loss_probability:.0%}."
    )


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
            cards = str(extra_stats.get("kaarten", "")).strip()
            substitutes = str(extra_stats.get("invallers", "")).strip()
            saved_notes = [
                f"**Speelstijl (press / zone / corners):** {tactics}" if tactics else "",
                f"**Leerpunten:** {evaluation}" if evaluation else "",
                f"**Extra statistieken – kaarten:** {cards}" if cards else "",
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
