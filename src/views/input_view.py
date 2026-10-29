import json
from datetime import date
from pathlib import Path

import streamlit as st

from src.calculations import get_all_matches, get_opponents_by_schedule
from src.constants import ASSIST_OPTIONS, OPPONENTS, PLAYERS

ALL_MATCHES_FILE = Path(__file__).resolve().parents[2] / "data" / "all_matches.json"
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
        # Sorteer altijd op ronde en datum
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


def _get_opponent(match: dict[str, object]) -> str:
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
    location = str(match.get("locatie", "")).strip()
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


def _is_esgh_fixture(match: dict[str, object]) -> bool:
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


def _poule_match_label(match: dict[str, object]) -> str:
    score_str = (
        f"{match.get('score_thuis')}-{match.get('score_uit')}"
        if match.get("gespeeld")
        else "Gepland"
    )
    return (
        f"Ronde {match.get('ronde', '?')} ({match.get('datum', '?')}): "
        f"{match.get('thuis')} - {match.get('uit')} [{score_str}]"
    )


def _render_poule_input() -> None:
    st.subheader("Poule-uitslag toevoegen")
    try:
        all_matches = _load_all_matches_file()
    except ValueError as error:
        st.error(str(error))
        return

    # Geplande wedstrijden van overige teams
    scheduled_matches = [
        m for m in all_matches
        if not m.get("gespeeld") and not _is_esgh_fixture(m)
    ]

    if not scheduled_matches:
        st.info("Er zijn geen geplande wedstrijden van andere teams om van een uitslag te voorzien.")
    else:
        labels = [_poule_match_label(m) for m in scheduled_matches]
        selected_label = st.selectbox("Geplande wedstrijd", labels, key="poule_scheduled_select")
        selected_match = scheduled_matches[labels.index(selected_label)]

        col1, col2 = st.columns(2)
        with col1:
            home_score = st.number_input(f"Score {selected_match['thuis']}", min_value=0, step=1)
        with col2:
            away_score = st.number_input(f"Score {selected_match['uit']}", min_value=0, step=1)

        if st.button("Uitslag opslaan", type="primary"):
            selected_match["score_thuis"] = int(home_score)
            selected_match["score_uit"] = int(away_score)
            selected_match["gespeeld"] = True
            _save_all_matches_file(all_matches)
            st.success(f"Uitslag {selected_match['thuis']} - {selected_match['uit']} opgeslagen!")
            st.rerun()

    with st.expander("Eerdere competitie-uitslagen aanpassen", expanded=False):
        played_matches = [
            m for m in all_matches
            if m.get("gespeeld") and not _is_esgh_fixture(m)
        ]
        if not played_matches:
            st.info("Geen eerdere uitslagen gevonden.")
            return

        played_labels = [_poule_match_label(m) for m in played_matches]
        prev_label = st.selectbox("Selecteer gespeelde wedstrijd", played_labels)
        prev_match = played_matches[played_labels.index(prev_label)]

        col1, col2 = st.columns(2)
        with col1:
            new_home = st.number_input(
                f"Score {prev_match['thuis']}",
                min_value=0,
                value=int(prev_match.get("score_thuis") or 0),
                step=1,
                key="prev_home"
            )
        with col2:
            new_away = st.number_input(
                f"Score {prev_match['uit']}",
                min_value=0,
                value=int(prev_match.get("score_uit") or 0),
                step=1,
                key="prev_away"
            )

        if st.button("Uitslag bijwerken"):
            prev_match["score_thuis"] = int(new_home)
            prev_match["score_uit"] = int(new_away)
            _save_all_matches_file(all_matches)
            st.success("Uitslag bijgewerkt!")
            st.rerun()


def _render_scheduled_match_input() -> None:
    st.subheader("Geplande wedstrijd toevoegen")
    match_date = st.date_input("Datum", value=date.today())
    teams = [_ESHG_TEAM, *(t for t in OPPONENTS if t != "Overig / Oefenwedstrijd")]

    col1, col2 = st.columns(2)
    with col1:
        home_team = st.selectbox("Thuisploeg", teams)
    with col2:
        away_options = [t for t in teams if t != home_team]
        away_team = st.selectbox("Uitploeg", away_options)

    all_matches = _load_all_matches_file()
    existing_rounds = [int(m["ronde"]) for m in all_matches if m.get("ronde") is not None]
    ronde = st.number_input(
        "Speelronde",
        min_value=1,
        max_value=30,
        value=min(30, max(existing_rounds, default=0) + 1),
        step=1,
    )

    if st.button("Geplande wedstrijd opslaan", type="primary"):
        record = {
            "match_id": f"poule_{int(ronde)}_{match_date.isoformat()}_{home_team}_{away_team}".replace(" ", "_"),
            "ronde": int(ronde),
            "datum": match_date.isoformat(),
            "thuis": home_team,
            "uit": away_team,
            "score_thuis": None,
            "score_uit": None,
            "gespeeld": False,
            "resultaat": None,
            "punten": None,
            "kwarten_bijgehouden": False,
            "kwarten": None,
            "corners_bijgehouden": False,
            "corners": None,
            "goals": [],
            "notities": {},
            "extra_stats": {},
        }
        all_matches.append(record)
        _save_all_matches_file(all_matches)
        st.success(f"Wedstrijd {home_team} - {away_team} toegevoegd aan ronde {int(ronde)}!")
        st.rerun()


def render_input_view() -> None:
    st.title("🏑 Wedstrijdbeheer ESHG")

    input_type = st.radio(
        "Type invoer",
        ["Eigen wedstrijd ESHG", "Poule-uitslag toevoegen", "Geplande wedstrijd toevoegen"],
        horizontal=True,
    )
    if input_type == "Poule-uitslag toevoegen":
        _render_poule_input()
        return
    if input_type == "Geplande wedstrijd toevoegen":
        _render_scheduled_match_input()
        return

    all_matches = _load_all_matches_file()
    eshg_matches = [m for m in all_matches if _is_esgh_fixture(m)]

    mode = st.radio(
        "Modus",
        ["Bestaande wedstrijd bewerken / data aanvullen", "Nieuwe wedstrijd toevoegen"],
        horizontal=True,
    )
    editing_existing = mode == "Bestaande wedstrijd bewerken / data aanvullen"

    selected_match = None
    if editing_existing:
        if not eshg_matches:
            st.warning("Geen wedstrijden gevonden.")
            return
        match_labels = [
            f"Ronde {m.get('ronde', '?')} ({m.get('datum', '?')}): "
            f"{_get_opponent(m)} [{'Gespeeld' if m.get('gespeeld') else 'Gepland'}]"
            for m in eshg_matches
        ]
        selected_label = st.selectbox("Selecteer wedstrijd", match_labels)
        selected_match = eshg_matches[match_labels.index(selected_label)]

    st.subheader("1. Wedstrijdgegevens")
    c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
    with c1:
        match_date = st.date_input(
            "Datum",
            value=date.fromisoformat(str(selected_match["datum"])) if selected_match and selected_match.get("datum") else date.today()
        )
    with c2:
        ronde = st.number_input(
            "Speelronde",
            min_value=1,
            max_value=30,
            value=int(selected_match.get("ronde") or 1) if selected_match else 1
        )
    with c3:
        opp_default = _get_opponent(selected_match) or OPPONENTS[0]
        opp_options = list(OPPONENTS)
        if opp_default not in opp_options:
            opp_options.append(opp_default)
        opponent = st.selectbox("Tegenstander", opp_options, index=opp_options.index(opp_default))
    with c4:
        loc_default = 0 if _get_location(selected_match) == "Thuis" else 1
        locatie = st.radio("Locatie", ["Thuis", "Uit"], index=loc_default, horizontal=True)

    st.subheader("2. Scores")
    quarter_data = _as_dict(selected_match.get("kwarten")) if selected_match else {}
    track_quarters = st.checkbox(
        "Scores per kwart zijn bijgehouden",
        value=bool(selected_match and selected_match.get("kwarten_bijgehouden"))
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
                eshg_quarter_values.append(int(c.number_input(f"Q{i+1}", min_value=0, max_value=20, value=eq[i], key=f"eq_{i}")))
        with col2:
            st.markdown(f"**{opponent}**")
            qc = st.columns(4)
            for i, c in enumerate(qc):
                opponent_quarter_values.append(int(c.number_input(f"Q{i+1}", min_value=0, max_value=20, value=oq[i], key=f"oq_{i}")))
        eshg_total = sum(eshg_quarter_values)
        opponent_total = sum(opponent_quarter_values)
    else:
        c1, c2 = st.columns(2)
        eshg_total = int(c1.number_input("Goals ESHG", min_value=0, value=_get_total_score(selected_match, "eshg")))
        opponent_total = int(c2.number_input("Goals Tegenstander", min_value=0, value=_get_total_score(selected_match, "tegenstander")))

    resultaat, punten = _determine_result(eshg_total, opponent_total)
    is_played = match_date <= date.today()

    st.subheader("3. Doelpuntenmakers & assists")
    goals = []
    existing_goals = selected_match.get("goals", []) if selected_match else []
    if eshg_total > 0:
        for idx in range(eshg_total):
            prev_g = existing_goals[idx] if idx < len(existing_goals) else {}
            c1, c2, c3, c4 = st.columns([1, 3, 3, 2])
            c1.write(f"Goal #{idx+1}")
            maker = c2.selectbox(
                "Maker",
                PLAYERS,
                index=PLAYERS.index(prev_g.get("maker")) if prev_g.get("maker") in PLAYERS else 0,
                key=f"maker_{idx}"
            )
            assist = c3.selectbox(
                "Assist",
                ASSIST_OPTIONS,
                index=ASSIST_OPTIONS.index(prev_g.get("assist") or "Geen assist") if (prev_g.get("assist") or "Geen assist") in ASSIST_OPTIONS else 0,
                key=f"assist_{idx}"
            )
            g_type = c4.selectbox(
                "Type",
                GOAL_TYPES,
                index=GOAL_TYPES.index(prev_g.get("type", "Veldgoal")) if prev_g.get("type") in GOAL_TYPES else 0,
                key=f"type_{idx}"
            )
            goals.append({
                "maker": maker,
                "assist": None if assist == "Geen assist" else assist,
                "type": g_type
            })

    st.subheader("4. Strafcorners")
    track_corners = st.checkbox(
        "Strafcorners bijgehouden",
        value=bool(selected_match and selected_match.get("corners_bijgehouden"))
    )
    corners_data = _as_dict(selected_match.get("corners")) if selected_match else {}
    cv_total = cv_scored = ct_total = ct_scored = 0
    if track_corners:
        c1, c2, c3, c4 = st.columns(4)
        conv = sum(1 for g in goals if g.get("type") == "Strafcorner")
        cv_total = int(c1.number_input("Corners ESHG", min_value=conv, value=max(int(corners_data.get("voor_totaal", 0)), conv)))
        cv_scored = int(c2.number_input("Benut ESHG", min_value=conv, max_value=max(conv, cv_total), value=conv, disabled=True))
        ct_total = int(c3.number_input("Corners tegen", min_value=0, value=int(corners_data.get("tegen_totaal", 0))))
        ct_scored = int(c4.number_input("Benut tegen", min_value=0, max_value=max(0, ct_total), value=min(int(corners_data.get("tegen_gescoord", 0)), ct_total)))

    st.subheader("5. Notities & Analyse")
    notes = _as_dict(selected_match.get("notities")) if selected_match else {}
    tactics = st.text_input("Tactiek / Speelstijl tegenstander", value=str(notes.get("tactiek", "")))
    evaluatie = st.text_area("Evaluatie ESHG", value=str(notes.get("evaluatie", "")))

    extra_stats = _as_dict(selected_match.get("extra_stats")) if selected_match else {}
    with st.expander("Extra statistieken"):
        kaarten = st.text_input("Kaarten", value=str(extra_stats.get("kaarten", "")))
        invallers = st.text_input("Invallers / Afwezigen", value=str(extra_stats.get("invallers", "")))

    if st.button("Wedstrijd opslaan", type="primary"):
        thuis_team = _ESHG_TEAM if locatie == "Thuis" else opponent
        uit_team = opponent if locatie == "Thuis" else _ESHG_TEAM
        score_thuis = eshg_total if locatie == "Thuis" else opponent_total
        score_uit = opponent_total if locatie == "Thuis" else eshg_total

        record = {
            **(selected_match or {}),
            "match_id": selected_match.get("match_id") if selected_match else f"{match_date.isoformat()}_{opponent.replace(' ', '_')}",
            "ronde": int(ronde),
            "datum": match_date.isoformat(),
            "thuis": thuis_team,
            "uit": uit_team,
            "score_thuis": score_thuis if is_played else None,
            "score_uit": score_uit if is_played else None,
            "gespeeld": is_played,
            "resultaat": resultaat if is_played else "Gepland",
            "punten": punten if is_played else 0,
            "kwarten_bijgehouden": track_quarters,
            "kwarten": {"eshg": eshg_quarter_values, "tegenstander": opponent_quarter_values} if track_quarters else None,
            "corners_bijgehouden": track_corners,
            "corners": {"voor_totaal": cv_total, "voor_gescoord": cv_scored, "tegen_totaal": ct_total, "tegen_gescoord": ct_scored} if track_corners else None,
            "goals": goals,
            "notities": {"tactiek": tactics, "evaluatie": evaluatie},
            "extra_stats": {"kaarten": kaarten, "invallers": invallers},
        }

        if editing_existing and selected_match:
            idx = all_matches.index(selected_match)
            all_matches[idx] = record
        else:
            all_matches.append(record)

        _save_all_matches_file(all_matches)
        st.success(f"Wedstrijd tegen {opponent} succesvol opgeslagen!")
        st.rerun()