import json
from datetime import date
from pathlib import Path

import streamlit as st

from src.constants import ASSIST_OPTIONS, OPPONENTS, PLAYERS

# Ondersteun zowel src/input_view.py als src/views/input_view.py
def _resolve_data_file() -> Path:
    p2 = Path(__file__).resolve().parents[2] / "data" / "all_matches.json"
    if p2.parent.exists():
        return p2
    return Path(__file__).resolve().parents[1] / "data" / "all_matches.json"

ALL_MATCHES_FILE = _resolve_data_file()
GOAL_TYPES = ["Veldgoal", "Strafcorner", "Strafbal (PS)"]
_ESHG_TEAM = "Don Quishoot H3"


def _load_all_matches_file() -> list[dict[str, object]]:
    if not ALL_MATCHES_FILE.exists():
        return []
    try:
        with ALL_MATCHES_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError(f"Het wedstrijdbestand kan niet worden gelezen: {error}") from error
    return data if isinstance(data, list) else []


def _save_all_matches_file(records: list[dict[str, object]]) -> None:
    try:
        ALL_MATCHES_FILE.parent.mkdir(parents=True, exist_ok=True)
        records.sort(
            key=lambda m: (
                m.get("ronde") if m.get("ronde") is not None else 999,
                str(m.get("datum", "")),
            )
        )
        with ALL_MATCHES_FILE.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except OSError as error:
        raise ValueError(f"De wedstrijden konden niet worden opgeslagen: {error}") from error


def _get_opponent(match: dict[str, object] | None) -> str:
    if match is None:
        return ""
    opponent = str(match.get("tegenstander", "")).strip()
    if opponent:
        return opponent
    home = str(match.get("thuis", "")).strip()
    away = str(match.get("uit", "")).strip()
    if home.casefold() == _ESHG_TEAM.casefold():
        return away
    if away.casefold() == _ESHG_TEAM.casefold():
        return home
    return ""


def _get_location(match: dict[str, object] | None) -> str:
    if match is None:
        return "Thuis"
    location = str(match.get("locatie", "")).strip().capitalize()
    if location in ("Thuis", "Uit"):
        return location
    if str(match.get("thuis", "")).casefold() == _ESHG_TEAM.casefold():
        return "Thuis"
    return "Uit"


def _get_total_score(selected_match: dict[str, object] | None, team: str) -> int:
    if selected_match is None:
        return 0
    is_home = _get_location(selected_match) == "Thuis"
    if team == "eshg":
        val = selected_match.get("score_thuis") if is_home else selected_match.get("score_uit")
    else:
        val = selected_match.get("score_uit") if is_home else selected_match.get("score_thuis")
    
    if val is not None:
        try:
            return max(0, int(val))
        except (ValueError, TypeError):
            pass
    return 0


def _is_eshg_fixture(match: dict[str, object]) -> bool:
    return _ESHG_TEAM.casefold() in {
        str(match.get("thuis", "")).strip().casefold(),
        str(match.get("uit", "")).strip().casefold(),
    }


def _determine_result(eshg_goals: int, opp_goals: int) -> tuple[str, int]:
    if eshg_goals > opp_goals:
        return "W", 3
    if eshg_goals == opp_goals:
        return "G", 1
    return "V", 0


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


# ==============================================================================
# TAB 1: EIGEN WEDSTRIJD ESHG (UITGEBREID)
# ==============================================================================
def _render_eshg_input(all_matches: list[dict[str, object]]) -> None:
    eshg_matches = [m for m in all_matches if _is_eshg_fixture(m)]
    if not eshg_matches:
        st.warning("Geen wedstrijden voor Don Quishoot H3 gevonden in het wedstrijdbestand.")
        return

    # Sorteer chronologisch op ronde
    eshg_matches.sort(key=lambda m: (int(m.get("ronde") or 99), str(m.get("datum", ""))))

    # Default naar de eerstvolgende nog niet gespeelde wedstrijd
    unplayed_indices = [i for i, m in enumerate(eshg_matches) if not m.get("gespeeld")]
    default_idx = unplayed_indices[0] if unplayed_indices else 0

    match_labels = []
    for m in eshg_matches:
        opp = _get_opponent(m)
        loc = _get_location(m)
        if m.get("gespeeld"):
            sh = m.get("score_thuis")
            su = m.get("score_uit")
            status = f"Gespeeld ({sh}-{su})"
        else:
            status = "Gepland"
        match_labels.append(
            f"Ronde {m.get('ronde', '?')} ({m.get('datum', '?')}): {loc} vs {opp} [{status}]"
        )

    selected_label = st.selectbox("Selecteer wedstrijd", match_labels, index=default_idx)
    selected_idx = match_labels.index(selected_label)
    selected_match = eshg_matches[selected_idx]

    match_key = f"match_{selected_match.get('match_id', selected_idx)}"

    st.subheader("1. Wedstrijdgegevens")
    c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
    with c1:
        match_date = st.date_input(
            "Datum",
            value=date.fromisoformat(str(selected_match["datum"])) if selected_match.get("datum") else date.today(),
            key=f"d_{match_key}",
        )
    with c2:
        ronde = st.number_input(
            "Speelronde",
            min_value=1,
            max_value=30,
            value=int(selected_match.get("ronde") or 1),
            key=f"r_{match_key}",
        )
    with c3:
        opp_default = _get_opponent(selected_match) or OPPONENTS[0]
        opp_options = list(OPPONENTS)
        if opp_default not in opp_options:
            opp_options.append(opp_default)
        opponent = st.selectbox(
            "Tegenstander",
            opp_options,
            index=opp_options.index(opp_default),
            key=f"o_{match_key}",
        )
    with c4:
        loc_default = 0 if _get_location(selected_match) == "Thuis" else 1
        locatie = st.radio(
            "Locatie",
            ["Thuis", "Uit"],
            index=loc_default,
            horizontal=True,
            key=f"l_{match_key}",
        )

    st.subheader("2. Scores")
    quarter_data = _as_dict(selected_match.get("kwarten"))
    track_quarters = st.checkbox(
        "Scores per kwart zijn bijgehouden",
        value=bool(selected_match.get("kwarten_bijgehouden")),
        key=f"tq_{match_key}",
    )

    eshg_quarter_values = []
    opponent_quarter_values = []
    if track_quarters:
        col1, col2 = st.columns(2)
        eq = quarter_data.get("eshg", [0, 0, 0, 0]) or [0, 0, 0, 0]
        oq = quarter_data.get("tegenstander", [0, 0, 0, 0]) or [0, 0, 0, 0]
        with col1:
            st.markdown("**Don Quishoot H3**")
            qc = st.columns(4)
            for i, c in enumerate(qc):
                eshg_quarter_values.append(
                    int(c.number_input(f"Q{i+1}", min_value=0, max_value=20, value=eq[i], key=f"eq_{i}_{match_key}"))
                )
        with col2:
            st.markdown(f"**{opponent}**")
            qc = st.columns(4)
            for i, c in enumerate(qc):
                opponent_quarter_values.append(
                    int(c.number_input(f"Q{i+1}", min_value=0, max_value=20, value=oq[i], key=f"oq_{i}_{match_key}"))
                )
        eshg_total = sum(eshg_quarter_values)
        opponent_total = sum(opponent_quarter_values)
    else:
        c1, c2 = st.columns(2)
        eshg_total = int(
            c1.number_input("Goals ESHG", min_value=0, value=_get_total_score(selected_match, "eshg"), key=f"tot_e_{match_key}")
        )
        opponent_total = int(
            c2.number_input("Goals Tegenstander", min_value=0, value=_get_total_score(selected_match, "tegenstander"), key=f"tot_o_{match_key}")
        )

    resultaat, punten = _determine_result(eshg_total, opponent_total)
    res_label = {"W": "Winst", "G": "Gelijkspel", "V": "Verlies"}[resultaat]
    
    col_status, col_res = st.columns([1, 2])
    with col_status:
        match_is_played = st.checkbox("Wedstrijd is gespeeld", value=bool(selected_match.get("gespeeld", True)), key=f"played_{match_key}")
    with col_res:
        if match_is_played:
            st.info(f"**Eindstand: {eshg_total} - {opponent_total}** ({res_label} → **{punten}** punten)")
        else:
            st.caption("Wedstrijd staat als gepland geregistreerd.")

    st.subheader("3. Doelpuntenmakers & assists")
    goals = []
    existing_goals = selected_match.get("goals", [])
    if eshg_total > 0 and match_is_played:
        for idx in range(eshg_total):
            prev_g = existing_goals[idx] if idx < len(existing_goals) else {}
            c1, c2, c3, c4 = st.columns([1, 3, 3, 2])
            c1.write(f"Goal #{idx+1}")
            maker = c2.selectbox(
                "Maker",
                PLAYERS,
                index=PLAYERS.index(prev_g.get("maker")) if prev_g.get("maker") in PLAYERS else 0,
                key=f"m_{match_key}_{idx}",
            )
            assist = c3.selectbox(
                "Assist",
                ASSIST_OPTIONS,
                index=ASSIST_OPTIONS.index(prev_g.get("assist") or "Geen assist") if (prev_g.get("assist") or "Geen assist") in ASSIST_OPTIONS else 0,
                key=f"a_{match_key}_{idx}",
            )
            g_type = c4.selectbox(
                "Type",
                GOAL_TYPES,
                index=GOAL_TYPES.index(prev_g.get("type", "Veldgoal")) if prev_g.get("type") in GOAL_TYPES else 0,
                key=f"t_{match_key}_{idx}",
            )
            goals.append({
                "maker": maker,
                "assist": None if assist == "Geen assist" else assist,
                "type": g_type,
            })
    elif not match_is_played:
        st.caption("Doelpuntenmakers kunnen worden toegekend zodra de wedstrijd als gespeeld is gemarkeerd.")
    else:
        st.caption("Geen doelpunten voor ESHG in deze wedstrijd.")

    st.subheader("4. Strafcorners")
    track_corners = st.checkbox(
        "Strafcorners bijgehouden",
        value=bool(selected_match.get("corners_bijgehouden")),
        key=f"tc_{match_key}",
    )
    corners_data = _as_dict(selected_match.get("corners"))
    cv_total = cv_scored = ct_total = ct_scored = 0
    if track_corners and match_is_played:
        c1, c2, c3, c4 = st.columns(4)
        conv = sum(1 for g in goals if g.get("type") == "Strafcorner")
        cv_total = int(c1.number_input("Corners ESHG", min_value=conv, value=max(int(corners_data.get("voor_totaal", 0)), conv), key=f"c1_{match_key}"))
        cv_scored = int(c2.number_input("Benut ESHG", min_value=conv, max_value=max(conv, cv_total), value=conv, disabled=True, key=f"c2_{match_key}"))
        ct_total = int(c3.number_input("Corners tegen", min_value=0, value=int(corners_data.get("tegen_totaal", 0)), key=f"c3_{match_key}"))
        ct_scored = int(c4.number_input("Benut tegen", min_value=0, max_value=max(0, ct_total), value=min(int(corners_data.get("tegen_gescoord", 0)), ct_total), key=f"c4_{match_key}"))

    st.subheader("5. Notities & Analyse")
    notes = _as_dict(selected_match.get("notities"))
    tactics = st.text_input("Tactiek / Speelstijl tegenstander", value=str(notes.get("tactiek", "")), key=f"notes_t_{match_key}")
    evaluatie = st.text_area("Evaluatie ESHG", value=str(notes.get("evaluatie", "")), key=f"notes_e_{match_key}")

    extra_stats = _as_dict(selected_match.get("extra_stats"))
    with st.expander("Extra statistieken (optioneel)"):
        kaarten = st.text_input("Kaarten", value=str(extra_stats.get("kaarten", "")), key=f"ex_k_{match_key}")
        invallers = st.text_input("Invallers / Afwezigen", value=str(extra_stats.get("invallers", "")), key=f"ex_i_{match_key}")

    if st.button("Wedstrijd opslaan", type="primary"):
        thuis_team = _ESHG_TEAM if locatie == "Thuis" else opponent
        uit_team = opponent if locatie == "Thuis" else _ESHG_TEAM
        score_thuis = eshg_total if locatie == "Thuis" else opponent_total
        score_uit = opponent_total if locatie == "Thuis" else eshg_total

        selected_match["ronde"] = int(ronde)
        selected_match["datum"] = match_date.isoformat()
        selected_match["thuis"] = thuis_team
        selected_match["uit"] = uit_team
        selected_match["tegenstander"] = opponent
        selected_match["locatie"] = locatie
        selected_match["score_thuis"] = score_thuis if match_is_played else None
        selected_match["score_uit"] = score_uit if match_is_played else None
        selected_match["gespeeld"] = match_is_played
        selected_match["resultaat"] = resultaat if match_is_played else "Gepland"
        selected_match["punten"] = punten if match_is_played else 0
        selected_match["kwarten_bijgehouden"] = track_quarters
        selected_match["kwarten"] = {"eshg": eshg_quarter_values, "tegenstander": opponent_quarter_values} if track_quarters else None
        selected_match["corners_bijgehouden"] = track_corners
        selected_match["corners"] = {"voor_totaal": cv_total, "voor_gescoord": cv_scored, "tegen_totaal": ct_total, "tegen_gescoord": ct_scored} if track_corners else None
        selected_match["goals"] = goals
        selected_match["notities"] = {"tactiek": tactics, "evaluatie": evaluatie}
        selected_match["extra_stats"] = {"kaarten": kaarten, "invallers": invallers}

        _save_all_matches_file(all_matches)
        st.success(f"Wedstrijd tegen {opponent} succesvol opgeslagen!")
        st.rerun()


# ==============================================================================
# TAB 2: POULE-UITSLAGEN PER RONDE (BATCH INVOER)
# ==============================================================================
def _render_poule_by_round_input(all_matches: list[dict[str, object]]) -> None:
    st.subheader("Poule-uitslagen per speelronde")
    st.caption("Selecteer een speelronde om alle overige competitiewedstrijden in één keer in te vullen of bij te werken.")

    available_rounds = sorted({
        int(m["ronde"])
        for m in all_matches
        if m.get("ronde") is not None
    })
    if not available_rounds:
        st.warning("Geen speelrondes gevonden in de competitiedata.")
        return

    # Bepaal de eerste ronde met nog niet gespeelde poulewedstrijden
    unplayed_rounds = [
        int(m["ronde"])
        for m in all_matches
        if m.get("ronde") is not None
        and not _is_eshg_fixture(m)
        and not m.get("gespeeld")
    ]
    default_round_idx = 0
    if unplayed_rounds:
        next_r = min(unplayed_rounds)
        if next_r in available_rounds:
            default_round_idx = available_rounds.index(next_r)

    selected_round = st.selectbox("Kies speelronde", available_rounds, index=default_round_idx)

    # Toon ESHG wedstrijd in deze ronde ter info
    eshg_in_round = [m for m in all_matches if m.get("ronde") == selected_round and _is_eshg_fixture(m)]
    if eshg_in_round:
        e_match = eshg_in_round[0]
        e_stat = f"{e_match.get('score_thuis')}-{e_match.get('score_uit')}" if e_match.get("gespeeld") else "Gepland"
        st.info(
            f"🏑 **Eigen wedstrijd in ronde {selected_round}:** {e_match.get('thuis')} vs {e_match.get('uit')} "
            f"[{e_stat}] *(bewerken via tabblad 'Eigen wedstrijd ESHG')*"
        )
    else:
        st.info(f"Don Quishoot H3 is vrij in speelronde {selected_round}.")

    # Overige wedstrijden uit deze ronde
    round_matches = [
        m for m in all_matches
        if m.get("ronde") == selected_round and not _is_eshg_fixture(m)
    ]

    if not round_matches:
        st.info(f"Geen overige wedstrijden gevonden voor speelronde {selected_round}.")
        return

    # Formulier om alle uitslagen in één keer in te vullen zonder herladen per veld
    with st.form(key=f"poule_round_form_{selected_round}"):
        st.markdown("---")
        form_data = []

        for idx, match in enumerate(round_matches):
            col_match, col_sh, col_sep, col_su, col_check = st.columns([4, 1.5, 0.4, 1.5, 2])
            
            with col_match:
                st.markdown(
                    f"**{match['thuis']}** – **{match['uit']}**  \n"
                    f"<small style='color: gray;'>Datum: {match.get('datum', '-')}</small>",
                    unsafe_allow_html=True,
                )

            current_home = int(match["score_thuis"]) if match.get("score_thuis") is not None else 0
            current_away = int(match["score_uit"]) if match.get("score_uit") is not None else 0
            is_played_default = bool(match.get("gespeeld"))

            with col_sh:
                sh_val = st.number_input(
                    f"Score {match['thuis']}",
                    min_value=0,
                    max_value=30,
                    value=current_home,
                    key=f"sh_{selected_round}_{idx}",
                )

            with col_sep:
                st.markdown("<div style='text-align: center; margin-top: 32px; font-weight: bold;'>-</div>", unsafe_allow_html=True)

            with col_su:
                su_val = st.number_input(
                    f"Score {match['uit']}",
                    min_value=0,
                    max_value=30,
                    value=current_away,
                    key=f"su_{selected_round}_{idx}",
                )

            with col_check:
                st.write("")
                st.write("")
                played_val = st.checkbox(
                    "Gespeeld",
                    value=is_played_default,
                    key=f"pl_{selected_round}_{idx}",
                    help="Vink aan als de wedstrijd definitief gespeeld is.",
                )

            form_data.append((match, sh_val, su_val, played_val))
            st.markdown("---")

        submitted = st.form_submit_button(
            f"💾 Alle uitslagen van speelronde {selected_round} opslaan",
            type="primary",
            use_container_width=True,
        )

        if submitted:
            for match, sh, su, played in form_data:
                match["gespeeld"] = played
                if played:
                    match["score_thuis"] = int(sh)
                    match["score_uit"] = int(su)
                else:
                    match["score_thuis"] = None
                    match["score_uit"] = None

            _save_all_matches_file(all_matches)
            st.success(f"Uitslagen van speelronde {selected_round} succesvol bijgewerkt!")
            st.rerun()


# ==============================================================================
# MAIN RENDERER
# ==============================================================================
def render_input_view() -> None:
    st.title("🏑 Wedstrijdbeheer")

    try:
        all_matches = _load_all_matches_file()
    except ValueError as error:
        st.error(str(error))
        return

    input_tab = st.radio(
        "Type invoer",
        ["Eigen wedstrijd ESHG", "Poule-uitslagen per ronde"],
        horizontal=True,
    )

    if input_tab == "Eigen wedstrijd ESHG":
        _render_eshg_input(all_matches)
    else:
        _render_poule_by_round_input(all_matches)