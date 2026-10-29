import json
from datetime import date
from pathlib import Path

import streamlit as st

from src.calculations import get_opponents_by_schedule
from src.constants import ASSIST_OPTIONS, OPPONENTS, PLAYERS
from src.calculations import get_all_matches


DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "wedstrijden.json"
LEGACY_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "matches.json"
POULE_DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "poule_matches.json"
GOAL_TYPES = ["Veldgoal", "Strafcorner", "Strafbal (PS)"]
_ESHG_TEAM = "Don Quishoot H3"


def _load_matches() -> list[dict[str, object]]:
    records_by_key: dict[str, dict[str, object]] = {}
    for path in (LEGACY_DATA_FILE, DATA_FILE):
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (json.JSONDecodeError, OSError) as error:
            raise ValueError(f"Het wedstrijdbestand kan niet worden gelezen: {error}") from error

        if not isinstance(data, list) or not all(
            isinstance(match, dict) for match in data
        ):
            raise ValueError("Het wedstrijdbestand moet een lijst met wedstrijdobjecten bevatten.")

        for index, match in enumerate(data):
            match_id = str(match.get("match_id", "")).strip()
            opponent = _get_opponent(match).casefold()
            if not opponent:
                continue
            match_date = str(match.get("datum", "")).strip()
            key = (
                f"fixture:{match_date}:{opponent}"
                if match_date and opponent
                else f"id:{match_id}"
                if match_id
                else f"record:{path}:{index}"
            )
            records_by_key[key] = match
    return list(records_by_key.values())


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
    if str(match.get("uit", "")).casefold() == _ESHG_TEAM.casefold():
        return "Uit"
    return "Thuis"


def _get_total_score(
    selected_match: dict[str, object] | None, team: str
) -> int:
    if selected_match is None:
        return 0
    score = _as_dict(selected_match.get("score"))
    if team == "eshg":
        value = score.get("eshg", selected_match.get("score_eshg"))
        if value is None:
            value = (
                selected_match.get("score_uit")
                if _get_location(selected_match) == "Uit"
                else selected_match.get("score_thuis")
            )
    else:
        value = score.get(
            "tegenstander", selected_match.get("score_tegenstander")
        )
        if value is None:
            value = (
                selected_match.get("score_thuis")
                if _get_location(selected_match) == "Uit"
                else selected_match.get("score_uit")
            )

    if value is None:
        quarter_values = _as_dict(selected_match.get("kwarten")).get(team)
        if isinstance(quarter_values, list):
            value = sum(_stored_nonnegative_int(item, f"score {team}") for item in quarter_values)
    return _stored_nonnegative_int(value or 0, f"score {team}")


def _match_key(match: dict[str, object]) -> tuple[str, str]:
    return (
        str(match.get("datum", "")).strip(),
        _get_opponent(match).casefold(),
    )


def _load_editable_matches(
    saved_matches: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[int | None]]:
    editable_matches = list(saved_matches)
    saved_indexes = {
        _match_key(match): index for index, match in enumerate(saved_matches)
    }
    storage_indexes: list[int | None] = list(range(len(saved_matches)))

    try:
        scheduled_matches = get_all_matches()
    except ValueError as error:
        raise ValueError(f"Het ESHG-wedstrijdprogramma kon niet worden geladen: {error}") from error

    round_by_fixture: dict[tuple[str, str], object] = {}
    if POULE_DATA_FILE.exists():
        try:
            with POULE_DATA_FILE.open("r", encoding="utf-8") as file:
                poule_records = json.load(file)
        except (json.JSONDecodeError, OSError) as error:
            raise ValueError(f"Het poulebestand kon niet worden gelezen: {error}") from error
        if not isinstance(poule_records, list) or not all(
            isinstance(match, dict) for match in poule_records
        ):
            raise ValueError("Het poulebestand moet een lijst met wedstrijdobjecten bevatten.")
        for match in poule_records:
            if _get_opponent(match):
                round_by_fixture[_match_key(match)] = match.get("ronde", "?")

    for scheduled_match in scheduled_matches:
        home = str(scheduled_match.get("thuis", "")).strip()
        away = str(scheduled_match.get("uit", "")).strip()
        if _ESHG_TEAM.casefold() not in (home.casefold(), away.casefold()):
            continue

        opponent = away if home.casefold() == _ESHG_TEAM.casefold() else home
        fixture_key = (
            str(scheduled_match.get("datum", "")).strip(),
            opponent.casefold(),
        )
        if fixture_key in saved_indexes:
            continue

        is_home = home.casefold() == _ESHG_TEAM.casefold()
        eshg_score = (
            scheduled_match.get("score_thuis")
            if is_home
            else scheduled_match.get("score_uit")
        )
        opponent_score = (
            scheduled_match.get("score_uit")
            if is_home
            else scheduled_match.get("score_thuis")
        )
        played = (
            scheduled_match.get("gespeeld") is True
            and eshg_score is not None
            and opponent_score is not None
        )
        try:
            result, points = _determine_result(
                int(eshg_score or 0), int(opponent_score or 0)
            )
        except (TypeError, ValueError):
            result, points = "", 0

        editable_matches.append(
            {
                "match_id": (
                    f"poule_{fixture_key[0]}_{opponent}".replace(" ", "_")
                ),
                "ronde": round_by_fixture.get(fixture_key, "?"),
                "datum": fixture_key[0],
                "tegenstander": opponent,
                "locatie": "Thuis" if is_home else "Uit",
                "score": {
                    "eshg": int(eshg_score or 0),
                    "tegenstander": int(opponent_score or 0),
                },
                "resultaat": result if played else "Gepland",
                "punten": points,
                "kwarten_bijgehouden": False,
                "kwarten": None,
                "goals": [],
                "corners_bijgehouden": False,
                "corners": None,
                "_schedule_only": True,
            }
        )
        storage_indexes.append(None)

    ordered = sorted(
        zip(editable_matches, storage_indexes),
        key=lambda item: (
            str(item[0].get("datum", "")),
            _get_opponent(item[0]).casefold(),
        ),
        reverse=True,
    )
    return [match for match, _ in ordered], [index for _, index in ordered]


def _save_all_matches(records: list[dict[str, object]]) -> None:
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with DATA_FILE.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except OSError as error:
        raise ValueError(f"De wedstrijden konden niet worden opgeslagen: {error}") from error


def _load_poule_matches() -> list[dict[str, object]]:
    if POULE_DATA_FILE.exists():
        try:
            with POULE_DATA_FILE.open("r", encoding="utf-8") as file:
                records = json.load(file)
        except (json.JSONDecodeError, OSError) as error:
            raise ValueError(f"Het poulebestand kan niet worden gelezen: {error}") from error
        if not isinstance(records, list) or not all(
            isinstance(match, dict) for match in records
        ):
            raise ValueError("Het poulebestand moet een lijst met wedstrijdobjecten bevatten.")
    else:
        records = []

    return records


def _save_poule_matches(records: list[dict[str, object]]) -> None:
    try:
        POULE_DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with POULE_DATA_FILE.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except OSError as error:
        raise ValueError(f"De poule-uitslag kon niet worden opgeslagen: {error}") from error


def _update_scheduled_match_round(record: dict[str, object]) -> bool:
    if not POULE_DATA_FILE.exists():
        return False

    try:
        with POULE_DATA_FILE.open("r", encoding="utf-8") as file:
            records = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        raise ValueError(f"Het poulebestand kon niet worden gelezen: {error}") from error
    if not isinstance(records, list) or not all(
        isinstance(match, dict) for match in records
    ):
        raise ValueError("Het poulebestand moet een lijst met wedstrijdobjecten bevatten.")

    fixture_teams = {
        str(record.get("thuis", "")).casefold(),
        str(record.get("uit", "")).casefold(),
    }
    for existing in records:
        existing_teams = {
            str(existing.get("thuis", "")).casefold(),
            str(existing.get("uit", "")).casefold(),
        }
        if (
            str(existing.get("datum", "")) == str(record.get("datum", ""))
            and existing_teams == fixture_teams
            and existing.get("gespeeld") is False
        ):
            existing["ronde"] = record["ronde"]
            try:
                with POULE_DATA_FILE.open("w", encoding="utf-8") as file:
                    json.dump(records, file, ensure_ascii=False, indent=2)
                    file.write("\n")
            except OSError as error:
                raise ValueError(
                    f"De speelronde kon niet worden opgeslagen: {error}"
                ) from error
            return True
    return False


def _is_esgh_fixture(match: dict[str, object]) -> bool:
    return _ESHG_TEAM.casefold() in {
        str(match.get("thuis", "")).strip().casefold(),
        str(match.get("uit", "")).strip().casefold(),
    }


def _is_past_or_today(match: dict[str, object]) -> bool:
    try:
        return date.fromisoformat(str(match.get("datum", ""))) <= date.today()
    except ValueError:
        return False


def _poule_match_label(match: dict[str, object], index: int) -> str:
    return (
        f"Ronde {match.get('ronde', '?')} ({match.get('datum', '?')}): "
        f"{match.get('thuis', '?')} - {match.get('uit', '?')} — #{index + 1}"
    )


def _render_poule_input() -> None:
    st.subheader("Poule-uitslag toevoegen")
    try:
        matches = _load_poule_matches()
    except ValueError as error:
        st.error(str(error))
        return

    scheduled_indexes = [
        index
        for index, match in enumerate(matches)
        if match.get("gespeeld") is False
        and not _is_esgh_fixture(match)
        and match.get("thuis")
        and match.get("uit")
    ]
    scheduled_indexes.sort(
        key=lambda index: (
            str(matches[index].get("datum", "")),
            str(matches[index].get("thuis", "")).casefold(),
        )
    )

    if not scheduled_indexes:
        st.info("Er zijn geen geplande wedstrijden van andere teams om van een uitslag te voorzien.")
    else:
        scheduled_labels = [
            _poule_match_label(matches[index], index) for index in scheduled_indexes
        ]
        selected_label = st.selectbox(
            "Geplande wedstrijd",
            scheduled_labels,
            key="poule_scheduled_fixture",
        )
        selected_index = scheduled_indexes[scheduled_labels.index(selected_label)]
        selected_match = matches[selected_index]
        score_home_column, score_away_column = st.columns(2)
        with score_home_column:
            home_score = st.number_input(
                f"Score {selected_match['thuis']}",
                min_value=0,
                step=1,
                key=f"poule_score_home_{selected_index}",
            )
        with score_away_column:
            away_score = st.number_input(
                f"Score {selected_match['uit']}",
                min_value=0,
                step=1,
                key=f"poule_score_away_{selected_index}",
            )

        if st.button("Uitslag opslaan", type="primary"):
            if not _is_past_or_today(selected_match):
                st.error(
                    "Deze wedstrijd staat in de toekomst. De uitslag kan pas na de wedstrijddatum worden opgeslagen."
                )
                return

            selected_match["score_thuis"] = int(home_score)
            selected_match["score_uit"] = int(away_score)
            selected_match["gespeeld"] = True
            try:
                _save_poule_matches(matches)
            except ValueError as error:
                st.error(str(error))
                return
            st.success(
                f"Uitslag {selected_match['thuis']} - {selected_match['uit']} opgeslagen."
            )

    with st.expander("Eerdere competitie-uitslagen aanpassen", expanded=False):
        played_indexes = [
            index
            for index, match in enumerate(matches)
            if match.get("gespeeld") is True
            and not _is_esgh_fixture(match)
            and _is_past_or_today(match)
            and match.get("score_thuis") is not None
            and match.get("score_uit") is not None
        ]
        played_indexes.sort(
            key=lambda index: (
                str(matches[index].get("datum", "")),
                str(matches[index].get("thuis", "")).casefold(),
            ),
            reverse=True,
        )
        if not played_indexes:
            st.info("Er zijn geen eerdere competitie-uitslagen om aan te passen.")
            return

        played_labels = [
            _poule_match_label(matches[index], index) for index in played_indexes
        ]
        previous_label = st.selectbox(
            "Selecteer eerdere uitslag",
            played_labels,
            key="poule_previous_result",
        )
        previous_index = played_indexes[played_labels.index(previous_label)]
        previous_match = matches[previous_index]
        previous_home_column, previous_away_column = st.columns(2)
        with previous_home_column:
            previous_home_score = st.number_input(
                f"Nieuwe score {previous_match['thuis']}",
                min_value=0,
                value=int(previous_match["score_thuis"]),
                step=1,
                key=f"poule_previous_home_{previous_index}",
            )
        with previous_away_column:
            previous_away_score = st.number_input(
                f"Nieuwe score {previous_match['uit']}",
                min_value=0,
                value=int(previous_match["score_uit"]),
                step=1,
                key=f"poule_previous_away_{previous_index}",
            )
        if st.button("Uitslag aanpassen"):
            previous_match["score_thuis"] = int(previous_home_score)
            previous_match["score_uit"] = int(previous_away_score)
            try:
                _save_poule_matches(matches)
            except ValueError as error:
                st.error(str(error))
                return
            st.success(
                f"Uitslag {previous_match['thuis']} - {previous_match['uit']} aangepast."
            )


def _render_scheduled_match_input() -> None:
    st.subheader("Geplande wedstrijd toevoegen")
    st.caption(
        "Sla een wedstrijd zonder uitslag op. De wedstrijd telt pas mee voor de stand "
        "wanneer er een uitslag is ingevuld."
    )
    match_date = st.date_input(
        "Datum", value=date.today(), key="scheduled_match_date"
    )

    teams = [
        _ESHG_TEAM,
        *(team for team in OPPONENTS if team != "Overig / Oefenwedstrijd"),
    ]
    home_column, away_column = st.columns(2)
    with home_column:
        home_team = st.selectbox("Thuisploeg", teams, key="scheduled_match_home")
    with away_column:
        away_options = [team for team in teams if team != home_team]
        away_team = st.selectbox("Uitploeg", away_options, key="scheduled_match_away")

    try:
        existing_matches = get_all_matches()
    except ValueError as error:
        st.error(f"Het wedstrijdprogramma kon niet worden geladen: {error}")
        return

    try:
        existing_rounds = [
            int(match["ronde"])
            for match in existing_matches
            if match.get("ronde") is not None
        ]
    except (ValueError, TypeError, OverflowError):
        st.error("De bestaande speelrondes konden niet worden gelezen.")
        return
    round_number = st.number_input(
        "Speelronde",
        min_value=1,
        max_value=30,
        value=min(30, max(existing_rounds, default=0) + 1),
        step=1,
        key="scheduled_match_round",
    )

    if st.button("Geplande wedstrijd opslaan", type="primary"):
        fixture_teams = {home_team.casefold(), away_team.casefold()}
        matching_fixture = next(
            (
                match
                for match in existing_matches
                if str(match.get("datum", "")) == match_date.isoformat()
                and {
                    str(match.get("thuis", "")).casefold(),
                    str(match.get("uit", "")).casefold(),
                }
                == fixture_teams
            ),
            None,
        )
        if matching_fixture and matching_fixture.get("gespeeld") is True:
            st.error("Deze wedstrijd is op deze datum al als gespeeld opgeslagen.")
            return

        record: dict[str, object] = {
            "match_id": (
                f"poule_{int(round_number)}_{match_date.isoformat()}_"
                f"{home_team}_{away_team}".replace(" ", "_")
            ),
            "datum": match_date.isoformat(),
            "thuis": home_team,
            "uit": away_team,
            "score_thuis": None,
            "score_uit": None,
            "ronde": int(round_number),
            "gespeeld": False,
        }
        try:
            round_updated = _update_scheduled_match_round(record)
            if not round_updated:
                matches = _load_poule_matches()
                matches.append(record)
                _save_poule_matches(matches)
        except ValueError as error:
            st.error(str(error))
            return
        action = "bijgewerkt" if round_updated else "opgeslagen"
        st.success(
            f"Wedstrijd {home_team} - {away_team} {action} voor speelronde "
            f"{int(round_number)}."
        )


def _determine_result(eshg_goals: int, opp_goals: int) -> tuple[str, int]:
    """Bepaalt resultaat (W/G/V) en KNHB-competitiepunten."""
    if eshg_goals > opp_goals:
        return "W", 3
    if eshg_goals == opp_goals:
        return "G", 1
    return "V", 0


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _stored_nonnegative_int(value: object, field: str, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"De opgeslagen waarde voor '{field}' is ongeldig.") from error
    if number < 0 or (maximum is not None and number > maximum):
        raise ValueError(f"De opgeslagen waarde voor '{field}' valt buiten het toegestane bereik.")
    return number


def _quarter_defaults(
    selected_match: dict[str, object] | None,
    team: str,
    legacy_score: object,
) -> list[int]:
    if selected_match is None:
        return [0, 0, 0, 0]

    quarters = _as_dict(selected_match.get("kwarten")).get(team)
    if isinstance(quarters, list) and len(quarters) == 4:
        return [
            _stored_nonnegative_int(value, f"{team}, kwart {quarter}", maximum=20)
            for quarter, value in enumerate(quarters, start=1)
        ]

    score = _as_dict(selected_match.get("score"))
    if team == "eshg":
        total = score.get("eshg", legacy_score)
    else:
        total = score.get("tegenstander", legacy_score)
    score_total = _stored_nonnegative_int(total, f"score {team}")
    if score_total > 80:
        raise ValueError(f"De opgeslagen score voor '{team}' is hoger dan 80.")
    return [min(20, max(0, score_total - quarter * 20)) for quarter in range(4)]


def _get_match_date(selected_match: dict[str, object] | None) -> date:
    if selected_match is None or not selected_match.get("datum"):
        return date.today()
    try:
        return date.fromisoformat(str(selected_match["datum"]))
    except ValueError as error:
        raise ValueError("De opgeslagen wedstrijddatum is ongeldig.") from error


def render_input_view() -> None:
    st.title("🏑 Wedstrijdbeheer ESHG")

    input_type = st.radio(
        "Type invoer",
        [
            "Eigen wedstrijd ESHG",
            "Poule-uitslag toevoegen",
            "Geplande wedstrijd toevoegen",
        ],
        horizontal=True,
        key="input_type",
    )
    if input_type == "Poule-uitslag toevoegen":
        _render_poule_input()
        return
    if input_type == "Geplande wedstrijd toevoegen":
        _render_scheduled_match_input()
        return

    try:
        saved_matches = _load_matches()
    except ValueError as error:
        st.error(str(error))
        return

    mode = st.radio(
        "Modus",
        ["Nieuwe wedstrijd toevoegen", "Bestaande wedstrijd bewerken / data aanvullen"],
        horizontal=True,
    )

    matches = saved_matches
    storage_indexes: list[int | None] = list(range(len(saved_matches)))
    selected_match: dict[str, object] | None = None
    edit_idx: int | None = None
    editing_existing = mode == "Bestaande wedstrijd bewerken / data aanvullen"
    if editing_existing:
        try:
            matches, storage_indexes = _load_editable_matches(saved_matches)
        except ValueError as error:
            st.error(str(error))
            return
        if not matches:
            st.warning("Er zijn nog geen opgeslagen wedstrijden om te bewerken.")
            return

        match_labels = [
            f"Ronde {match.get('ronde', '?')} ({match.get('datum', '?')}): "
            f"{_get_opponent(match) or '?'} [{match.get('resultaat', '?')}]"
            f"{' (schema)' if match.get('_schedule_only') else ''}"
            for idx, match in enumerate(matches)
        ]
        selected_label = st.selectbox("Selecteer wedstrijd", match_labels)
        selected_idx = match_labels.index(selected_label)
        edit_idx = storage_indexes[selected_idx]
        selected_match = matches[selected_idx]

    match_key = (
        f"match_{selected_match.get('match_id', edit_idx)}"
        if editing_existing and selected_match
        else "new_match"
    )

    st.subheader("1. Wedstrijdgegevens")
    c1, c2, c3, c4 = st.columns([2, 1, 2, 2])
    try:
        date_default = _get_match_date(selected_match)
    except ValueError as error:
        st.error(str(error))
        return

    with c1:
        match_date = st.date_input("Datum", value=date_default, key=f"datum_{match_key}")
    with c2:
        round_value = (
            selected_match.get("ronde", len(matches) + 1)
            if selected_match
            else len(matches) + 1
        )
        try:
            round_default = int(round_value)
        except (TypeError, ValueError):
            round_default = 1
        ronde = st.number_input(
            "Speelronde",
            min_value=1,
            max_value=30,
            value=max(1, min(30, round_default)),
            key=f"ronde_{match_key}",
        )
    with c3:
        try:
            scheduled_opponents = get_opponents_by_schedule(list(OPPONENTS))
        except ValueError as error:
            st.error(f"Het programma kon niet worden geladen: {error}")
            return
        opponent_default = (
            _get_opponent(selected_match) or OPPONENTS[0]
            if selected_match
            else scheduled_opponents[0]
        )
        opponent_options = scheduled_opponents
        if opponent_default not in opponent_options:
            opponent_options.append(opponent_default)
        opponent = st.selectbox(
            "Tegenstander",
            opponent_options,
            index=opponent_options.index(opponent_default),
            key=f"tegenstander_{match_key}",
            help="Geordend op datum van de eerstvolgende geplande wedstrijd.",
        )
    with c4:
        location_default = 0 if _get_location(selected_match) == "Thuis" else 1
        locatie = st.radio(
            "Locatie",
            ["Thuis", "Uit"],
            index=location_default,
            horizontal=True,
            key=f"locatie_{match_key}",
        )

    quarter_data = _as_dict(selected_match.get("kwarten")) if selected_match else {}
    quarter_tracking_default = (
        not selected_match
        or (
            selected_match.get("kwarten_bijgehouden") is not False
            and isinstance(quarter_data.get("eshg"), list)
            and len(quarter_data["eshg"]) == 4
            and isinstance(quarter_data.get("tegenstander"), list)
            and len(quarter_data["tegenstander"]) == 4
        )
    )
    st.subheader("2. Scores")
    track_quarters = st.checkbox(
        "Scores per kwart zijn bijgehouden",
        value=quarter_tracking_default,
        key=f"track_quarters_{match_key}",
    )
    try:
        eshg_quarters = _quarter_defaults(
            selected_match,
            "eshg",
            selected_match.get("score_eshg", 0) if selected_match else 0,
        )
        opponent_quarters = _quarter_defaults(
            selected_match,
            "tegenstander",
            selected_match.get("score_tegenstander", 0) if selected_match else 0,
        )
        eshg_total_default = _get_total_score(selected_match, "eshg")
        opponent_total_default = _get_total_score(selected_match, "tegenstander")
    except ValueError as error:
        st.error(str(error))
        return

    eshg_quarter_values: list[int] = []
    opponent_quarter_values: list[int] = []
    if track_quarters:
        st.caption(
            "Vul de doelpunten per kwart in; de eindscore, uitslag en punten worden automatisch berekend."
        )
        eshg_column, opponent_column = st.columns(2)
        with eshg_column:
            st.markdown("**Don Quishoot H3 (ESHG)**")
            quarter_columns = st.columns(4)
            for quarter, column in enumerate(quarter_columns):
                eshg_quarter_values.append(
                    int(
                        column.number_input(
                            f"Q{quarter + 1}",
                            min_value=0,
                            max_value=20,
                            value=eshg_quarters[quarter],
                            key=f"q{quarter + 1}_e_{match_key}",
                        )
                    )
                )
        with opponent_column:
            st.markdown(f"**{opponent}**")
            quarter_columns = st.columns(4)
            for quarter, column in enumerate(quarter_columns):
                opponent_quarter_values.append(
                    int(
                        column.number_input(
                            f"Q{quarter + 1}",
                            min_value=0,
                            max_value=20,
                            value=opponent_quarters[quarter],
                            key=f"q{quarter + 1}_o_{match_key}",
                        )
                    )
                )
        eshg_total = sum(eshg_quarter_values)
        opponent_total = sum(opponent_quarter_values)
    else:
        st.caption(
            "De eindscore wordt rechtstreeks ingevoerd; de toewijzing van ESHG-doelpunten blijft beschikbaar."
        )
        total_columns = st.columns(2)
        with total_columns[0]:
            eshg_total = int(
                st.number_input(
                    "Totaal doelpunten ESHG",
                    min_value=0,
                    value=eshg_total_default,
                    key=f"total_e_{match_key}",
                )
            )
        with total_columns[1]:
            opponent_total = int(
                st.number_input(
                    "Totaal doelpunten tegenstander",
                    min_value=0,
                    value=opponent_total_default,
                    key=f"total_o_{match_key}",
                )
            )

    resultaat, punten = _determine_result(eshg_total, opponent_total)
    match_is_played = match_date <= date.today()
    if match_is_played:
        result_label = {"W": "Winst", "G": "Gelijkspel", "V": "Verlies"}[resultaat]
        st.info(
            f"**Eindstand: {eshg_total} - {opponent_total}** "
            f"({result_label} → **{punten}** punten)"
        )
    else:
        st.info(
            f"**Ingevoerde stand: {eshg_total} - {opponent_total}** "
            "Deze toekomstige wedstrijd blijft gepland en telt nog niet mee als gespeeld."
        )

    st.subheader("3. Doelpuntenmakers & assists")
    goals: list[dict[str, object]] = []
    existing_goals = selected_match.get("goals", []) if selected_match else []
    if not isinstance(existing_goals, list) and selected_match:
        existing_goals = selected_match.get("doelpunten", [])
    if not isinstance(existing_goals, list):
        existing_goals = []

    if eshg_total == 0:
        st.caption("Geen doelpunten voor ESHG in deze wedstrijd.")
    else:
        for goal_idx in range(eshg_total):
            previous_goal = (
                _as_dict(existing_goals[goal_idx])
                if goal_idx < len(existing_goals)
                else {}
            )
            scorer_default = str(
                previous_goal.get(
                    "maker", previous_goal.get("doelpuntenmaker", PLAYERS[0])
                )
            )
            scorer_options = list(PLAYERS)
            if scorer_default not in scorer_options:
                scorer_options.append(scorer_default)
            assist_default = previous_goal.get("assist") or "Geen assist"
            assist_default = str(assist_default)
            assist_options = list(ASSIST_OPTIONS)
            if assist_default not in assist_options:
                assist_options.append(assist_default)
            previous_type = str(previous_goal.get("type", "Veldgoal"))
            goal_type_options = list(GOAL_TYPES)
            if previous_type not in goal_type_options:
                goal_type_options.append(previous_type)

            number_column, scorer_column, assist_column, type_column = st.columns(
                [1, 3, 3, 2]
            )
            with number_column:
                st.write(f"Goal #{goal_idx + 1}")
            with scorer_column:
                maker = st.selectbox(
                    "Doelpuntenmaker",
                    scorer_options,
                    index=scorer_options.index(scorer_default),
                    key=f"goal_maker_{match_key}_{goal_idx}",
                )
            with assist_column:
                assist = st.selectbox(
                    "Assist",
                    assist_options,
                    index=assist_options.index(assist_default),
                    key=f"goal_assist_{match_key}_{goal_idx}",
                )
            with type_column:
                goal_type = st.selectbox(
                    "Type",
                    goal_type_options,
                    index=goal_type_options.index(previous_type),
                    key=f"goal_type_{match_key}_{goal_idx}",
                )

            goals.append(
                {
                    "maker": maker,
                    "assist": None if assist == "Geen assist" else assist,
                    "type": goal_type,
                }
            )

    st.subheader("4. Strafcorners")
    converted_corners = sum(
        1 for goal in goals if goal.get("type") == "Strafcorner"
    )
    corners = _as_dict(selected_match.get("corners")) if selected_match else {}
    if selected_match and not corners:
        corners = _as_dict(selected_match.get("strafcorners"))
    corner_tracking_default = (
        not selected_match
        or (
            selected_match.get("corners_bijgehouden") is not False
            and bool(corners)
        )
    )
    track_corners = st.checkbox(
        "Strafcorners zijn bijgehouden",
        value=corner_tracking_default,
        key=f"track_corners_{match_key}",
    )
    cv_total = cv_scored = ct_total = ct_scored = 0
    if track_corners:
        corners_column_1, corners_column_2, corners_column_3, corners_column_4 = st.columns(4)
    else:
        st.caption("Strafcornerstatistieken worden voor deze wedstrijd niet bijgehouden.")
    try:
        old_for_total = _stored_nonnegative_int(
            corners.get("voor_totaal", corners.get("voor", 0)), "corners ESHG totaal"
        )
        old_against_total = _stored_nonnegative_int(
            corners.get("tegen_totaal", corners.get("tegen", 0)), "corners tegen totaal"
        )
        old_against_scored = _stored_nonnegative_int(
            corners.get("tegen_gescoord", 0), "corners tegen benut"
        )
    except ValueError as error:
        st.error(str(error))
        return
    if track_corners:
        with corners_column_1:
            cv_total = int(
                st.number_input(
                    "Corners ESHG totaal",
                    min_value=converted_corners,
                    value=max(old_for_total, converted_corners),
                    key=f"corners_for_{match_key}",
                )
            )
        with corners_column_2:
            cv_scored = int(
                st.number_input(
                    "Corners ESHG benut",
                    min_value=converted_corners,
                    max_value=cv_total,
                    value=converted_corners,
                    disabled=True,
                    key=f"corners_for_scored_auto_{match_key}",
                )
            )
        with corners_column_3:
            ct_total = int(
                st.number_input(
                    "Corners tegen totaal",
                    min_value=0,
                    value=old_against_total,
                    key=f"corners_against_{match_key}",
                )
            )
        with corners_column_4:
            ct_scored = int(
                st.number_input(
                    "Corners tegen benut",
                    min_value=0,
                    max_value=ct_total,
                    value=min(old_against_scored, ct_total),
                    key=f"corners_against_scored_{match_key}",
                )
            )

    st.subheader("5. Notities & analyse")
    notes = _as_dict(selected_match.get("notities")) if selected_match else {}
    tactics = st.text_input(
        "Speelstijl tegenstander (press, gevaarlijke spelers)",
        value=str(notes.get("tactiek", "")),
        key=f"tactiek_{match_key}",
    )
    evaluation = st.text_area(
        "ESHG evaluatie / leerpunten",
        value=str(notes.get("evaluatie", "")),
        key=f"evaluatie_{match_key}",
    )

    with st.expander("Extra statistieken toevoegen (optioneel)"):
        st.caption("Voeg hier extra velden toe die niet standaard in het formulier zitten.")
        extra_stats = _as_dict(selected_match.get("extra_stats")) if selected_match else {}
        cards = st.text_input(
            "Kaarten (bijv. Groen: Joep Q2)",
            value=str(extra_stats.get("kaarten", "")),
            key=f"kaarten_{match_key}",
        )
        substitutes = st.text_input(
            "Invallers / Afwezigen",
            value=str(extra_stats.get("invallers", "")),
            key=f"invallers_{match_key}",
        )

    button_label = "Wijzigingen bijwerken" if editing_existing else "Wedstrijd opslaan"
    if st.button(button_label, type="primary"):
        match_id = (
            selected_match.get(
                "match_id",
                f"{match_date.isoformat()}_{str(opponent).replace(' ', '_')}",
            )
            if selected_match
            else f"{match_date.isoformat()}_{str(opponent).replace(' ', '_')}"
        )
        record: dict[str, object] = {
            **{
                key: value
                for key, value in (selected_match or {}).items()
                if key != "_schedule_only"
            },
            "match_id": match_id,
            "ronde": int(ronde),
            "datum": match_date.isoformat(),
            "tegenstander": opponent,
            "locatie": locatie,
            "score": {"eshg": eshg_total, "tegenstander": opponent_total},
            "resultaat": resultaat if match_is_played else "Gepland",
            "punten": punten if match_is_played else 0,
            "gespeeld": match_is_played,
            "kwarten_bijgehouden": track_quarters,
            "kwarten": (
                {
                    "eshg": eshg_quarter_values,
                    "tegenstander": opponent_quarter_values,
                }
                if track_quarters
                else None
            ),
            "goals": goals,
            "corners_bijgehouden": track_corners,
            "corners": (
                {
                    "voor_totaal": cv_total,
                    "voor_gescoord": cv_scored,
                    "tegen_totaal": ct_total,
                    "tegen_gescoord": ct_scored,
                }
                if track_corners
                else None
            ),
            "notities": {"tactiek": tactics, "evaluatie": evaluation},
            "extra_stats": {"kaarten": cards, "invallers": substitutes},
        }

        if not editing_existing:
            matches.append(record)
        elif edit_idx is None:
            saved_matches.append(record)
        else:
            saved_matches[edit_idx] = record

        try:
            _save_all_matches(matches if not editing_existing else saved_matches)
        except ValueError as error:
            st.error(str(error))
            return

        success_action = "bijgewerkt" if editing_existing else "opgeslagen"
        st.success(f"Wedstrijd tegen {opponent} succesvol {success_action}!")
