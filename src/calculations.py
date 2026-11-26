import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.constants import PLAYERS

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_ALL_MATCHES_FILE = _DATA_DIR / "all_matches.json"
_PITCHERS_FILE = _DATA_DIR / "pitchers.json"
_ESHG_TEAM = "Don Quishoot H3"
_MONTE_CARLO_RANDOM_SEED = 42
_OWN_GOAL_LABEL = "Eigen doelpunt tegenstander"
_PLAYER_STAT_COLUMNS = [
    "Positie",
    "Speler",
    "GS",
    "Goals",
    "Assists",
    "Totaal_G_A",
    "Veldgoals",
    "Strafcorners",
    "Strafballen",
    "Punten",
    "Kaarten",
]


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as file:
            records = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Bestand kan niet worden gelezen ({path}): {error}") from error
    return records if isinstance(records, list) else []


def get_all_matches() -> list[dict[str, Any]]:
    """Laad alle competitiewedstrijden rechtstreeks uit all_matches.json."""
    return _load_json_records(_ALL_MATCHES_FILE)


def _get_scoring_matches() -> list[dict[str, Any]]:
    """Laad alle gespeelde wedstrijden van ESHG inclusief doelpunten en details."""
    completed = []
    for match in get_all_matches():
        if not match.get("gespeeld"):
            continue
        home = _team_key(str(match.get("thuis", "")))
        away = _team_key(str(match.get("uit", "")))
        if _team_key(_ESHG_TEAM) in (home, away):
            completed.append(match)
    return completed


def _match_has_result(match: dict[str, Any]) -> bool:
    """Controleert of een wedstrijd gespeeld is en een geldige uitslag heeft."""
    if match.get("gespeeld"):
        return (
            _score(match.get("score_thuis")) is not None
            and _score(match.get("score_uit")) is not None
        )
    return False


def _goal_records(match: dict[str, Any]) -> list[dict[str, Any]]:
    goals = match.get("goals")
    if not isinstance(goals, list):
        return []
    return [goal for goal in goals if isinstance(goal, dict)]


def _person_name(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _empty_player_stats() -> dict[str, int]:
    return {
        "GS": 0,
        "Punten": 0,
        "Goals": 0,
        "Veldgoals": 0,
        "Strafcorners": 0,
        "Strafballen": 0,
        "Assists": 0,
        "Groen": 0,
        "Geel": 0,
        "Rood": 0,
    }


def _normalize_date(value: object) -> str:
    if value is None:
        return ""
    date_text = str(value).strip()
    if not date_text:
        return ""

    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(date_text, date_format).date().isoformat()
        except ValueError:
            continue
    return date_text


def _team_key(team: str) -> str:
    return " ".join(team.split()).casefold()


def _score(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, str)):
        return None
    try:
        score = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if score < 0:
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return score


def _round_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        rnd = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return rnd if rnd > 0 else None


def _valid_played_score(match: dict[str, Any]) -> tuple[int, int] | None:
    if match.get("gespeeld") is not True:
        return None
    home_score = _score(match.get("score_thuis"))
    away_score = _score(match.get("score_uit"))
    if home_score is None or away_score is None:
        return None
    return home_score, away_score


def _card_records(match: dict[str, Any]) -> list[dict[str, str]]:
    extra_stats = match.get("extra_stats")
    if not isinstance(extra_stats, dict):
        return []
    raw_cards = extra_stats.get("kaarten")
    if not isinstance(raw_cards, list):
        return []

    cards: list[dict[str, str]] = []
    for item in raw_cards:
        if not isinstance(item, dict):
            continue
        speler = _person_name(item.get("speler"))
        kaart_type = _person_name(item.get("type"))
        if speler and kaart_type in ("Groen", "Geel", "Rood"):
            cards.append({"speler": speler, "type": kaart_type})
    return cards


def _format_cards_summary(groen: int, geel: int, rood: int) -> str:
    parts = []
    if rood > 0:
        parts.append(f"{rood}🟥")
    if geel > 0:
        parts.append(f"{geel}🟨")
    if groen > 0:
        parts.append(f"{groen}🟩")
    return " ".join(parts) if parts else "—"


def _match_eshg_outcome(match: dict[str, Any]) -> tuple[int, int, str, int] | None:
    scores = _valid_played_score(match)
    if scores is None:
        return None
    home = str(match.get("thuis", "")).strip()
    if _team_key(home) == _team_key(_ESHG_TEAM):
        eshg_goals, opp_goals = scores
    else:
        eshg_goals, opp_goals = scores[1], scores[0]

    if eshg_goals > opp_goals:
        return eshg_goals, opp_goals, "W", 3
    if eshg_goals == opp_goals:
        return eshg_goals, opp_goals, "G", 1
    return eshg_goals, opp_goals, "V", 0


def _match_present_players(match: dict[str, Any], squad_set: set[str]) -> set[str]:
    raw_attendees = match.get("aanwezigen")
    if isinstance(raw_attendees, list):
        return {
            name
            for item in raw_attendees
            if (name := _person_name(item)) and name in squad_set
        }

    inferred: set[str] = set()
    for goal in _goal_records(match):
        maker = _person_name(goal.get("maker"))
        assist = _person_name(goal.get("assist"))
        if maker in squad_set:
            inferred.add(maker)
        if assist in squad_set:
            inferred.add(assist)
    for card in _card_records(match):
        if card["speler"] in squad_set:
            inferred.add(card["speler"])
    return inferred


def calculate_player_stats() -> pd.DataFrame:
    """Calculate attendance, points, goals, assists, and cards for the squad."""
    player_names = [player for player in PLAYERS if player != _OWN_GOAL_LABEL]
    squad_set = set(player_names)
    stats: dict[str, dict[str, int]] = {
        player: _empty_player_stats() for player in player_names
    }

    for match in _get_scoring_matches():
        outcome = _match_eshg_outcome(match)
        if outcome is None:
            continue
        _, _, _, match_points = outcome

        for present_player in _match_present_players(match, squad_set):
            player_stats = stats.setdefault(present_player, _empty_player_stats())
            player_stats["GS"] += 1
            player_stats["Punten"] += match_points

        for goal in _goal_records(match):
            maker = _person_name(goal.get("maker"))
            if maker and maker != _OWN_GOAL_LABEL:
                player_stats = stats.setdefault(maker, _empty_player_stats())
                player_stats["Goals"] += 1
                goal_type = _person_name(goal.get("type"))
                if goal_type == "Veldgoal":
                    player_stats["Veldgoals"] += 1
                elif goal_type == "Strafcorner":
                    player_stats["Strafcorners"] += 1
                elif goal_type in ("Strafbal", "Strafbal (PS)"):
                    player_stats["Strafballen"] += 1

            assist = _person_name(goal.get("assist"))
            if assist and assist not in ("Geen assist", _OWN_GOAL_LABEL):
                assist_stats = stats.setdefault(assist, _empty_player_stats())
                assist_stats["Assists"] += 1

        for card in _card_records(match):
            card_player = card["speler"]
            if card_player != _OWN_GOAL_LABEL:
                card_stats = stats.setdefault(card_player, _empty_player_stats())
                card_stats[card["type"]] += 1

    rows = [
        {
            "Speler": player,
            "GS": player_stats["GS"],
            "Punten": player_stats["Punten"],
            "Goals": player_stats["Goals"],
            "Veldgoals": player_stats["Veldgoals"],
            "Strafcorners": player_stats["Strafcorners"],
            "Strafballen": player_stats["Strafballen"],
            "Assists": player_stats["Assists"],
            "Totaal_G_A": player_stats["Goals"] + player_stats["Assists"],
            "Kaarten": _format_cards_summary(
                player_stats["Groen"],
                player_stats["Geel"],
                player_stats["Rood"],
            ),
        }
        for player, player_stats in stats.items()
    ]

    frame = pd.DataFrame(rows)
    frame = frame.sort_values(
        ["Goals", "Assists", "Totaal_G_A", "Punten", "GS"],
        ascending=[False, False, False, False, False],
        kind="stable",
    ).reset_index(drop=True)
    frame.insert(0, "Positie", range(1, len(frame) + 1))
    return frame[_PLAYER_STAT_COLUMNS]


def get_top_duos() -> pd.DataFrame:
    """Return up to five most frequent assist-to-scorer combinations."""
    duo_counts: dict[tuple[str, str], int] = {}
    for match in _get_scoring_matches():
        for goal in _goal_records(match):
            assist = _person_name(goal.get("assist"))
            maker = _person_name(goal.get("maker"))
            if (
                not assist
                or assist in ("Geen assist", _OWN_GOAL_LABEL)
                or not maker
                or maker == _OWN_GOAL_LABEL
            ):
                continue
            duo = (assist, maker)
            duo_counts[duo] = duo_counts.get(duo, 0) + 1

    duos = sorted(
        duo_counts.items(),
        key=lambda item: (-item[1], item[0][0].casefold(), item[0][1].casefold()),
    )[:5]
    return pd.DataFrame(
        [
            {"Aangever": assist, "Afmaker": maker, "Aantal": count}
            for (assist, maker), count in duos
        ],
        columns=["Aangever", "Afmaker", "Aantal"],
    )


def get_player_match_timeline(player: str) -> pd.DataFrame:
    """Return played matches where a player was present, including goals, assists, points, and cards."""
    squad_set = {p for p in PLAYERS if p != _OWN_GOAL_LABEL}
    timeline: list[dict[str, str | int]] = []

    for match in _get_scoring_matches():
        outcome = _match_eshg_outcome(match)
        if outcome is None:
            continue
        eshg_goals, opp_goals, res_code, match_points = outcome

        goals = _goal_records(match)
        cards = _card_records(match)
        present_players = _match_present_players(match, squad_set)

        player_goals = sum(
            _person_name(goal.get("maker")) == player for goal in goals
        )
        player_assists = sum(
            _person_name(goal.get("assist")) == player for goal in goals
        )
        player_cards = [
            card["type"] for card in cards if card["speler"] == player
        ]

        if (
            player not in present_players
            and not player_goals
            and not player_assists
            and not player_cards
        ):
            continue

        opponent = _person_name(match.get("tegenstander"))
        if not opponent:
            home = str(match.get("thuis", "")).strip()
            away = str(match.get("uit", "")).strip()
            opponent = away if _team_key(home) == _team_key(_ESHG_TEAM) else home

        involvement = []
        if player_goals:
            involvement.append("Goal" if player_goals == 1 else f"{player_goals} goals")
        if player_assists:
            involvement.append(
                "Assist" if player_assists == 1 else f"{player_assists} assists"
            )

        timeline.append(
            {
                "Datum": _normalize_date(match.get("datum")),
                "Tegenstander": opponent,
                "Uitslag": f"{res_code} ({eshg_goals}-{opp_goals})",
                "Punten": match_points,
                "Bijdrage": " + ".join(involvement) if involvement else "—",
                "Kaart": ", ".join(player_cards) if player_cards else "—",
            }
        )

    timeline.sort(key=lambda row: str(row["Datum"]), reverse=True)
    return pd.DataFrame(
        timeline,
        columns=["Datum", "Tegenstander", "Uitslag", "Punten", "Bijdrage", "Kaart"],
    )


def get_opponents_by_schedule(opponents: list[str]) -> list[str]:
    """Order opponents with their next scheduled ESHG fixture first by date."""
    next_fixture_by_opponent: dict[str, str] = {}
    for match in get_all_matches():
        if match.get("gespeeld") is not False:
            continue

        home = str(match.get("thuis", "")).strip()
        away = str(match.get("uit", "")).strip()
        if _team_key(home) == _team_key(_ESHG_TEAM):
            opponent = away
        elif _team_key(away) == _team_key(_ESHG_TEAM):
            opponent = home
        else:
            continue

        opponent_key = _team_key(opponent)
        match_date = _normalize_date(match.get("datum"))
        if opponent_key and (
            opponent_key not in next_fixture_by_opponent
            or match_date < next_fixture_by_opponent[opponent_key]
        ):
            next_fixture_by_opponent[opponent_key] = match_date

    return [
        opponent
        for _, opponent in sorted(
            enumerate(opponents),
            key=lambda item: (
                next_fixture_by_opponent.get(_team_key(item[1]), "\uffff"),
                item[0],
            ),
        )
    ]


def _team_match_result(
    match: dict[str, Any], team: str
) -> dict[str, Any] | None:
    scores = _valid_played_score(match)
    if scores is None:
        return None

    home = str(match.get("thuis", "")).strip()
    away = str(match.get("uit", "")).strip()
    if _team_key(team) == _team_key(home):
        opponent = away
        goals_for, goals_against = scores
        location = "Thuis"
    elif _team_key(team) == _team_key(away):
        opponent = home
        goals_for, goals_against = scores[1], scores[0]
        location = "Uit"
    else:
        return None

    result = (
        "W"
        if goals_for > goals_against
        else "V"
        if goals_for < goals_against
        else "G"
    )
    return {
        "datum": _normalize_date(match.get("datum")),
        "tegenstander": opponent,
        "locatie": location,
        "score": f"{goals_for}-{goals_against}",
        "doelpunten_voor": goals_for,
        "doelpunten_tegen": goals_against,
        "resultaat": result,
        "notities": match.get("notities", {}),
        "extra_stats": match.get("extra_stats", {}),
    }


def get_head_to_head(opponent: str) -> dict[str, Any]:
    """Return ESHG's played results and saved notes against an opponent."""
    opponent_key = _team_key(opponent)
    meetings: list[dict[str, Any]] = []

    for match in get_all_matches():
        eshg_result = _team_match_result(match, _ESHG_TEAM)
        if eshg_result is None or _team_key(eshg_result["tegenstander"]) != opponent_key:
            continue
        meetings.append(eshg_result)

    meetings.sort(key=lambda meeting: meeting["datum"])
    wins = sum(meeting["resultaat"] == "W" for meeting in meetings)
    draws = sum(meeting["resultaat"] == "G" for meeting in meetings)
    losses = sum(meeting["resultaat"] == "V" for meeting in meetings)
    goal_difference = sum(
        meeting["doelpunten_voor"] - meeting["doelpunten_tegen"]
        for meeting in meetings
    )
    return {
        "gespeeld": len(meetings),
        "winst": wins,
        "gelijk": draws,
        "verlies": losses,
        "doelsaldo": goal_difference,
        "wedstrijden": meetings,
        "notities": meetings[-1].get("notities", {}) if meetings else {},
        "extra_stats": meetings[-1].get("extra_stats", {}) if meetings else {},
    }


def get_opponent_form(opponent: str, n_matches: int = 5) -> list[dict[str, Any]]:
    """Return the opponent's most recent played matches, from their perspective."""
    if n_matches <= 0:
        return []

    matches: list[dict[str, Any]] = []
    for match in get_all_matches():
        result = _team_match_result(match, opponent)
        if result is not None:
            matches.append(result)

    matches.sort(key=lambda item: item["datum"], reverse=True)
    return matches[:n_matches]


def get_common_opponents_comparison(opponent: str) -> pd.DataFrame:
    """Compare the latest result ESHG and an opponent had against each shared team."""
    results_by_team: dict[str, dict[str, dict[str, Any]]] = {
        _team_key(_ESHG_TEAM): {},
        _team_key(opponent): {},
    }
    matches = get_all_matches()
    for match in matches:
        for team in (_ESHG_TEAM, opponent):
            result = _team_match_result(match, team)
            if result is None:
                continue
            shared_team_key = _team_key(result["tegenstander"])
            if shared_team_key in results_by_team:
                continue
            previous = results_by_team[_team_key(team)].get(shared_team_key)
            if previous is None or result["datum"] > previous["datum"]:
                results_by_team[_team_key(team)][shared_team_key] = result

    eshg_results = results_by_team[_team_key(_ESHG_TEAM)]
    opponent_results = results_by_team[_team_key(opponent)]
    common_teams = eshg_results.keys() & opponent_results.keys()
    team_names = {
        _team_key(str(match.get(team_field, ""))): str(match.get(team_field, ""))
        for match in matches
        for team_field in ("thuis", "uit")
        if match.get(team_field)
    }

    def format_result(result: dict[str, Any]) -> str:
        return f"{result['resultaat']} {result['score']}"

    rows = [
        {
            "Gedeeld Team": team_names.get(team_key, team_key),
            "Uitslag ESHG": format_result(eshg_results[team_key]),
            "Uitslag Tegenstander": format_result(opponent_results[team_key]),
        }
        for team_key in sorted(
            common_teams, key=lambda key: team_names.get(key, key).casefold()
        )
    ]
    return pd.DataFrame(
        rows,
        columns=["Gedeeld Team", "Uitslag ESHG", "Uitslag Tegenstander"],
    )


def _team_recent_averages(
    matches: list[dict[str, Any]], team: str, n: int = 3
) -> tuple[float, float]:
    """Return goals-for and goals-against averages over a team's latest matches."""
    if n <= 0:
        return 0.0, 0.0

    played = [
        result
        for match in matches
        if (result := _team_match_result(match, team)) is not None
    ]
    played.sort(key=lambda result: result["datum"], reverse=True)
    recent = played[:n]
    if not recent:
        return 0.0, 0.0

    return (
        sum(result["doelpunten_voor"] for result in recent) / len(recent),
        sum(result["doelpunten_tegen"] for result in recent) / len(recent),
    )


def _common_opponents_expected_diff(
    matches: list[dict[str, Any]], team_a: str, team_b: str
) -> float:
    """Return the average relative goal difference against shared opponents."""
    goal_differences: dict[str, dict[str, list[int]]] = {
        _team_key(team_a): {},
        _team_key(team_b): {},
    }

    for match in matches:
        for team in (team_a, team_b):
            result = _team_match_result(match, team)
            if result is None:
                continue
            shared_opponent = _team_key(result["tegenstander"])
            goal_differences[_team_key(team)].setdefault(shared_opponent, []).append(
                result["doelpunten_voor"] - result["doelpunten_tegen"]
            )

    team_a_differences = goal_differences[_team_key(team_a)]
    team_b_differences = goal_differences[_team_key(team_b)]
    common_opponents = team_a_differences.keys() & team_b_differences.keys()
    if not common_opponents:
        return 0.0

    relative_differences = [
        sum(team_a_differences[opponent]) / len(team_a_differences[opponent])
        - sum(team_b_differences[opponent]) / len(team_b_differences[opponent])
        for opponent in common_opponents
    ]
    return sum(relative_differences) / len(relative_differences)


def calculate_standings(matches: list[dict[str, Any]]) -> pd.DataFrame:
    """Calculate team standings and sort by the KNHB ranking criteria."""
    standings: dict[str, dict[str, int | str]] = {}

    def ensure_team(name: str) -> dict[str, int | str]:
        key = _team_key(name)
        if key not in standings:
            standings[key] = {
                "Team": name,
                "GS": 0,
                "W": 0,
                "G": 0,
                "V": 0,
                "PT": 0,
                "DV": 0,
                "DT": 0,
                "DS": 0,
            }
        return standings[key]

    for match in matches:
        home = str(match.get("thuis", "")).strip()
        away = str(match.get("uit", "")).strip()
        if not home or not away:
            continue
        scores = _valid_played_score(match)
        if scores is None:
            continue

        home_standing = ensure_team(home)
        away_standing = ensure_team(away)
        home_score, away_score = scores
        home_standing["GS"] = int(home_standing["GS"]) + 1
        away_standing["GS"] = int(away_standing["GS"]) + 1
        home_standing["DV"] = int(home_standing["DV"]) + home_score
        home_standing["DT"] = int(home_standing["DT"]) + away_score
        away_standing["DV"] = int(away_standing["DV"]) + away_score
        away_standing["DT"] = int(away_standing["DT"]) + home_score

        if home_score > away_score:
            home_standing["W"] = int(home_standing["W"]) + 1
            home_standing["PT"] = int(home_standing["PT"]) + 3
            away_standing["V"] = int(away_standing["V"]) + 1
        elif home_score < away_score:
            away_standing["W"] = int(away_standing["W"]) + 1
            away_standing["PT"] = int(away_standing["PT"]) + 3
            home_standing["V"] = int(home_standing["V"]) + 1
        else:
            home_standing["G"] = int(home_standing["G"]) + 1
            home_standing["PT"] = int(home_standing["PT"]) + 1
            away_standing["G"] = int(away_standing["G"]) + 1
            away_standing["PT"] = int(away_standing["PT"]) + 1

    rows = list(standings.values())
    for row in rows:
        row["DS"] = int(row["DV"]) - int(row["DT"])
    rows.sort(
        key=lambda row: (
            -int(row["PT"]),
            -int(row["W"]),
            -int(row["DS"]),
            -int(row["DV"]),
            str(row["Team"]).casefold(),
        )
    )

    frame = pd.DataFrame(
        rows,
        columns=["Team", "GS", "W", "G", "V", "PT", "DV", "DT", "DS"],
    )
    frame.insert(0, "Pos", range(1, len(frame) + 1))
    return frame


def calculate_points_progression(
    matches: list[dict[str, Any]], mode: str = "matches"
) -> pd.DataFrame:
    """Bereken het cumulatieve puntenverloop per team op basis van gespeelde duels ('matches') of speelronde ('rounds')."""
    team_names: dict[str, str] = {}
    played_entries: list[dict[str, Any]] = []

    for index, match in enumerate(matches):
        home = str(match.get("thuis", "")).strip()
        away = str(match.get("uit", "")).strip()
        home_key = _team_key(home)
        away_key = _team_key(away)
        if not home_key or not away_key:
            continue

        team_names.setdefault(home_key, home)
        team_names.setdefault(away_key, away)

        scores = _valid_played_score(match)
        if scores is None:
            continue

        round_num = _round_int(match.get("ronde"))

        played_entries.append(
            {
                "datum": _normalize_date(match.get("datum")),
                "ronde": round_num,
                "index": index,
                "home_key": home_key,
                "away_key": away_key,
                "home_name": home,
                "away_name": away,
                "home_score": scores[0],
                "away_score": scores[1],
            }
        )

    if not played_entries or not team_names:
        return pd.DataFrame(
            columns=["Stap", "Team", "Positie", "Punten", "Ronde_Punten", "Gespeeld", "Detail"]
        )

    standings = calculate_standings(matches)
    positions_by_key: dict[str, int] = {}
    ordered_keys: list[str] = []
    for _, row in standings.iterrows():
        key = _team_key(str(row["Team"]))
        if key in team_names:
            positions_by_key[key] = int(row["Pos"])
            ordered_keys.append(key)

    for key in sorted(team_names, key=lambda k: team_names[k].casefold()):
        if key not in positions_by_key:
            positions_by_key[key] = len(ordered_keys) + 1
            ordered_keys.append(key)

    played_entries.sort(
        key=lambda item: (
            item["datum"],
            item["ronde"] if item["ronde"] is not None else 999,
            item["index"],
        )
    )

    rows: list[dict[str, Any]] = []

    if mode == "rounds":
        valid_rounds = [
            entry["ronde"] for entry in played_entries if entry["ronde"] is not None
        ]
        if not valid_rounds:
            return pd.DataFrame(
                columns=["Stap", "Team", "Positie", "Punten", "Ronde_Punten", "Gespeeld", "Detail"]
            )
        max_round = max(valid_rounds)

        team_round_events: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for entry in played_entries:
            rnd = entry["ronde"]
            if rnd is None:
                continue
            h_score, a_score = entry["home_score"], entry["away_score"]
            h_pts = 3 if h_score > a_score else (1 if h_score == a_score else 0)
            a_pts = 3 if a_score > h_score else (1 if a_score == h_score else 0)

            team_round_events.setdefault((entry["home_key"], rnd), []).append(
                {
                    "pts": h_pts,
                    "detail": f"+{h_pts} pt (vs {entry['away_name']} {h_score}-{a_score})",
                }
            )
            team_round_events.setdefault((entry["away_key"], rnd), []).append(
                {
                    "pts": a_pts,
                    "detail": f"+{a_pts} pt (@ {entry['home_name']} {a_score}-{h_score})",
                }
            )

        for team_key in ordered_keys:
            team_label = team_names[team_key]
            pos = positions_by_key[team_key]
            cumulative = 0
            rows.append(
                {
                    "Stap": 0,
                    "Team": team_label,
                    "Positie": pos,
                    "Punten": 0,
                    "Ronde_Punten": 0,
                    "Gespeeld": True,
                    "Detail": "Start seizoen",
                }
            )
            for rnd in range(1, max_round + 1):
                events = team_round_events.get((team_key, rnd), [])
                if events:
                    gained = sum(ev["pts"] for ev in events)
                    cumulative += gained
                    detail = " & ".join(ev["detail"] for ev in events)
                    played_flag = True
                else:
                    gained = 0
                    detail = "Vrij / nog niet gespeeld (+0 pt)"
                    played_flag = False

                rows.append(
                    {
                        "Stap": rnd,
                        "Team": team_label,
                        "Positie": pos,
                        "Punten": cumulative,
                        "Ronde_Punten": gained,
                        "Gespeeld": played_flag,
                        "Detail": detail,
                    }
                )
    else:
        team_matches: dict[str, list[dict[str, Any]]] = {key: [] for key in ordered_keys}
        for entry in played_entries:
            h_score, a_score = entry["home_score"], entry["away_score"]
            h_pts = 3 if h_score > a_score else (1 if h_score == a_score else 0)
            a_pts = 3 if a_score > h_score else (1 if a_score == h_score else 0)

            team_matches[entry["home_key"]].append(
                {
                    "pts": h_pts,
                    "detail": f"+{h_pts} pt (vs {entry['away_name']} {h_score}-{a_score})",
                }
            )
            team_matches[entry["away_key"]].append(
                {
                    "pts": a_pts,
                    "detail": f"+{a_pts} pt (@ {entry['home_name']} {a_score}-{h_score})",
                }
            )

        for team_key in ordered_keys:
            team_label = team_names[team_key]
            pos = positions_by_key[team_key]
            cumulative = 0
            rows.append(
                {
                    "Stap": 0,
                    "Team": team_label,
                    "Positie": pos,
                    "Punten": 0,
                    "Ronde_Punten": 0,
                    "Gespeeld": True,
                    "Detail": "Start seizoen",
                }
            )
            for match_num, ev in enumerate(team_matches[team_key], start=1):
                cumulative += ev["pts"]
                rows.append(
                    {
                        "Stap": match_num,
                        "Team": team_label,
                        "Positie": pos,
                        "Punten": cumulative,
                        "Ronde_Punten": ev["pts"],
                        "Gespeeld": True,
                        "Detail": ev["detail"],
                    }
                )

    return pd.DataFrame(
        rows,
        columns=["Stap", "Team", "Positie", "Punten", "Ronde_Punten", "Gespeeld", "Detail"],
    )


def calculate_elo_ratings(
    matches: list[dict[str, Any]], k_factor: int = 32, start_elo: float = 1500.0
) -> pd.DataFrame:
    """Calculate current team ELO ratings and played/remaining schedule strength."""
    team_names: dict[str, str] = {}
    for match in matches:
        for field in ("thuis", "uit"):
            team = str(match.get(field, "")).strip()
            if team:
                team_names.setdefault(_team_key(team), team)

    ratings = {team_key: start_elo for team_key in team_names}
    played_opponents: dict[str, list[str]] = {team_key: [] for team_key in team_names}
    remaining_opponents: dict[str, list[str]] = {
        team_key: [] for team_key in team_names
    }

    played_matches = []
    for index, match in enumerate(matches):
        home_key = _team_key(str(match.get("thuis", "")).strip())
        away_key = _team_key(str(match.get("uit", "")).strip())
        if not home_key or not away_key or home_key == away_key:
            continue
        scores = _valid_played_score(match)
        if scores is None:
            if match.get("gespeeld") is False:
                remaining_opponents[home_key].append(away_key)
                remaining_opponents[away_key].append(home_key)
            continue
        played_matches.append(
            (
                _normalize_date(match.get("datum")),
                index,
                home_key,
                away_key,
                scores[0],
                scores[1],
            )
        )

    for _, _, home_key, away_key, home_score, away_score in sorted(
        played_matches, key=lambda match: (match[0], match[1])
    ):
        home_rating = ratings[home_key]
        away_rating = ratings[away_key]
        expected_home = 1 / (1 + 10 ** ((away_rating - home_rating) / 400))
        actual_home = (
            1.0 if home_score > away_score else 0.5 if home_score == away_score else 0.0
        )
        goal_difference_multiplier = math.log1p(abs(home_score - away_score))
        multiplier = goal_difference_multiplier if goal_difference_multiplier else 1.0
        rating_change = k_factor * multiplier * (actual_home - expected_home)
        ratings[home_key] += rating_change
        ratings[away_key] -= rating_change
        played_opponents[home_key].append(away_key)
        played_opponents[away_key].append(home_key)

    official_standings = calculate_standings(matches)
    official_positions = {
        _team_key(str(row["Team"])): int(row["Pos"])
        for row in official_standings.to_dict("records")
    }
    rows = []
    for team_key, team in team_names.items():
        opponents_played = played_opponents[team_key]
        opponents_remaining = remaining_opponents[team_key]
        rows.append(
            {
                "Positie KNHB": official_positions.get(team_key, pd.NA),
                "Team": team,
                "ELO Rating": ratings[team_key],
                "ELO Verschil t.o.v. Start": ratings[team_key] - start_elo,
                "SoS Gespeeld": (
                    sum(ratings[opponent] for opponent in opponents_played)
                    / len(opponents_played)
                    if opponents_played
                    else 0.0
                ),
                "SoS Resterend": (
                    sum(ratings[opponent] for opponent in opponents_remaining)
                    / len(opponents_remaining)
                    if opponents_remaining
                    else 0.0
                ),
            }
        )

    frame = pd.DataFrame(
        rows,
        columns=[
            "Positie KNHB",
            "Team",
            "ELO Rating",
            "ELO Verschil t.o.v. Start",
            "SoS Gespeeld",
            "SoS Resterend",
        ],
    )
    return frame.sort_values(
        "ELO Rating", ascending=False, kind="stable"
    ).reset_index(drop=True)


def _poisson_pmf_list(expected_goals: float, max_goals: int = 16) -> list[float]:
    probs = [math.exp(-expected_goals)]
    for goals in range(1, max_goals + 1):
        probs.append(probs[-1] * expected_goals / goals)
    total = sum(probs)
    return [p / total for p in probs] if total > 0 else probs


def predict_match_outcome(
    matches: list[dict[str, Any]],
    team_a: str,
    team_b: str,
    model_type: str = "elo",
) -> dict[str, Any] | None:
    """Voorspel winkansen (W/G/V), teamprofielen en meest waarschijnlijke uitslagen tussen twee teams."""
    team_a_key = _team_key(team_a)
    team_b_key = _team_key(team_b)

    team_goals_for: dict[str, list[int]] = {}
    team_goals_against: dict[str, list[int]] = {}

    for match in matches:
        home_key = _team_key(str(match.get("thuis", "")).strip())
        away_key = _team_key(str(match.get("uit", "")).strip())
        if not home_key or not away_key or home_key == away_key:
            continue
        team_goals_for.setdefault(home_key, [])
        team_goals_for.setdefault(away_key, [])
        team_goals_against.setdefault(home_key, [])
        team_goals_against.setdefault(away_key, [])

        scores = _valid_played_score(match)
        if scores is not None:
            team_goals_for[home_key].append(scores[0])
            team_goals_against[home_key].append(scores[1])
            team_goals_for[away_key].append(scores[1])
            team_goals_against[away_key].append(scores[0])

    played_a = len(team_goals_for.get(team_a_key, []))
    played_b = len(team_goals_for.get(team_b_key, []))
    if played_a == 0 or played_b == 0:
        return None

    all_goals = [g for goals in team_goals_for.values() for g in goals]
    league_avg = sum(all_goals) / len(all_goals) if all_goals else 2.5

    raw_a_for = sum(team_goals_for[team_a_key]) / played_a
    raw_a_against = sum(team_goals_against[team_a_key]) / played_a
    raw_b_for = sum(team_goals_for[team_b_key]) / played_b
    raw_b_against = sum(team_goals_against[team_b_key]) / played_b

    seasonal_a = (raw_a_for + raw_b_against) / 2.0
    seasonal_b = (raw_b_for + raw_a_against) / 2.0

    rec_a_for, rec_a_against = _team_recent_averages(matches, team_a, n=3)
    rec_b_for, rec_b_against = _team_recent_averages(matches, team_b, n=3)
    recent_a = (rec_a_for + rec_b_against) / 2.0
    recent_b = (rec_b_for + rec_a_against) / 2.0

    rel_diff = _common_opponents_expected_diff(matches, team_a, team_b)
    common_a = max(0.2, league_avg + rel_diff / 2.0)
    common_b = max(0.2, league_avg - rel_diff / 2.0)

    elo_df = calculate_elo_ratings(matches)
    elo_dict = {
        _team_key(str(row["Team"])): float(row["ELO Rating"])
        for _, row in elo_df.iterrows()
    }
    elo_a = elo_dict.get(team_a_key, 1500.0)
    elo_b = elo_dict.get(team_b_key, 1500.0)
    elo_diff = elo_a - elo_b

    prior_weight = 4.0
    shrunk_a_for = (sum(team_goals_for[team_a_key]) + prior_weight * league_avg) / (played_a + prior_weight)
    shrunk_a_against = (sum(team_goals_against[team_a_key]) + prior_weight * league_avg) / (played_a + prior_weight)
    shrunk_b_for = (sum(team_goals_for[team_b_key]) + prior_weight * league_avg) / (played_b + prior_weight)
    shrunk_b_against = (sum(team_goals_against[team_b_key]) + prior_weight * league_avg) / (played_b + prior_weight)

    base_a = (shrunk_a_for * shrunk_b_against) / league_avg if league_avg > 0 else shrunk_a_for
    base_b = (shrunk_b_for * shrunk_a_against) / league_avg if league_avg > 0 else shrunk_b_for
    elo_shift = elo_diff / 400.0
    elo_lambda_a = max(0.2, base_a + elo_shift)
    elo_lambda_b = max(0.2, base_b - elo_shift)

    if model_type == "ensemble":
        lambda_a = 0.45 * elo_lambda_a + 0.25 * common_a + 0.20 * recent_a + 0.10 * seasonal_a
        lambda_b = 0.45 * elo_lambda_b + 0.25 * common_b + 0.20 * recent_b + 0.10 * seasonal_b
    elif model_type == "recent":
        lambda_a, lambda_b = recent_a, recent_b
    elif model_type == "gedeeld":
        lambda_a, lambda_b = common_a, common_b
    elif model_type == "seizoen":
        lambda_a, lambda_b = seasonal_a, seasonal_b
    else:
        lambda_a, lambda_b = elo_lambda_a, elo_lambda_b

    probs_a = _poisson_pmf_list(lambda_a)
    probs_b = _poisson_pmf_list(lambda_b)

    win_a = 0.0
    draw = 0.0
    win_b = 0.0
    score_matrix: list[tuple[int, int, float]] = []

    for ga, pa in enumerate(probs_a):
        for gb, pb in enumerate(probs_b):
            joint = pa * pb
            score_matrix.append((ga, gb, joint))
            if ga > gb:
                win_a += joint
            elif ga < gb:
                win_b += joint
            else:
                draw += joint

    score_matrix.sort(key=lambda item: item[2], reverse=True)
    top_scores = [
        {"score": f"{ga} - {gb}", "kans": prob}
        for ga, gb, prob in score_matrix[:3]
    ]

    def _attack_profile(goals_for_avg: float) -> str:
        if goals_for_avg >= league_avg + 0.45:
            return "Veel scorend"
        if goals_for_avg <= league_avg - 0.45:
            return "Moeizaam scorend"
        return "Gemiddeld scorend"

    def _defense_profile(goals_against_avg: float) -> str:
        if goals_against_avg <= league_avg - 0.45:
            return "Solide verdediging"
        if goals_against_avg >= league_avg + 0.45:
            return "Kwetsbaar achterin"
        return "Gemiddelde verdediging"

    expected_total = lambda_a + lambda_b
    if expected_total >= 2 * league_avg + 0.7:
        tempo_label = "Doelpuntrijk duel verwacht"
    elif expected_total <= 2 * league_avg - 0.7:
        tempo_label = "Gesloten, doelpuntarm duel verwacht"
    else:
        tempo_label = "Gemiddeld aantal doelpunten verwacht"

    return {
        "win_a": win_a,
        "draw": draw,
        "win_b": win_b,
        "lambda_a": lambda_a,
        "lambda_b": lambda_b,
        "elo_a": elo_a,
        "elo_b": elo_b,
        "elo_diff": elo_diff,
        "league_avg": league_avg,
        "tempo_label": tempo_label,
        "top_scores": top_scores,
        "profile_a": {
            "gespeeld": played_a,
            "voor_gem": raw_a_for,
            "tegen_gem": raw_a_against,
            "aanval_label": _attack_profile(raw_a_for),
            "verdediging_label": _defense_profile(raw_a_against),
        },
        "profile_b": {
            "gespeeld": played_b,
            "voor_gem": raw_b_for,
            "tegen_gem": raw_b_against,
            "aanval_label": _attack_profile(raw_b_for),
            "verdediging_label": _defense_profile(raw_b_against),
        },
    }


def run_monte_carlo_simulation(
    matches: list[dict[str, Any]], n_simulations: int = 1000, model_type: str = "standaard"
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Simulate the remaining pool fixtures and summarize final standings, points fan chart, and all rank thresholds."""
    if n_simulations <= 0:
        raise ValueError("n_simulations moet groter zijn dan nul.")

    team_names: dict[str, str] = {}
    played_matches: list[dict[str, Any]] = []
    remaining_matches: list[dict[str, Any]] = []
    team_goals_for: dict[str, list[int]] = {}
    team_goals_against: dict[str, list[int]] = {}
    all_rounds: list[int] = []
    played_rounds: list[int] = []

    for match in matches:
        home = str(match.get("thuis", "")).strip()
        away = str(match.get("uit", "")).strip()
        home_key = _team_key(home)
        away_key = _team_key(away)
        if not home_key or not away_key or home_key == away_key:
            continue
        team_names.setdefault(home_key, home)
        team_names.setdefault(away_key, away)
        team_goals_for.setdefault(home_key, [])
        team_goals_for.setdefault(away_key, [])
        team_goals_against.setdefault(home_key, [])
        team_goals_against.setdefault(away_key, [])

        rnd = _round_int(match.get("ronde"))
        if rnd is not None:
            all_rounds.append(rnd)

        scores = _valid_played_score(match)
        if scores is not None:
            home_score, away_score = scores
            if rnd is not None:
                played_rounds.append(rnd)
            played_matches.append(
                {
                    "thuis": home_key,
                    "uit": away_key,
                    "score_thuis": home_score,
                    "score_uit": away_score,
                    "ronde": rnd,
                }
            )
            team_goals_for[home_key].append(home_score)
            team_goals_against[home_key].append(away_score)
            team_goals_for[away_key].append(away_score)
            team_goals_against[away_key].append(home_score)
        elif match.get("gespeeld") is False:
            remaining_matches.append(
                {
                    "thuis": home_key,
                    "uit": away_key,
                    "ronde": rnd,
                }
            )

    pool_goals_for = [
        goal for goals in team_goals_for.values() for goal in goals
    ]
    pool_goals_against = [
        goal for goals in team_goals_against.values() for goal in goals
    ]
    fallback_for = sum(pool_goals_for) / len(pool_goals_for) if pool_goals_for else 2.5
    fallback_against = (
        sum(pool_goals_against) / len(pool_goals_against)
        if pool_goals_against
        else 2.5
    )

    if model_type == "aangepast":
        elo_df = calculate_elo_ratings(matches)
        elo_dict = {
            _team_key(str(row["Team"])): float(row["ELO Rating"])
            for _, row in elo_df.iterrows()
        }

        PRIOR_WEIGHT = 4
        league_avg = fallback_for

        shrunk_averages = {}
        for team_key in team_names:
            n_played = len(team_goals_for[team_key])
            gf = sum(team_goals_for[team_key])
            ga = sum(team_goals_against[team_key])

            avg_for = (gf + PRIOR_WEIGHT * league_avg) / (n_played + PRIOR_WEIGHT)
            avg_against = (ga + PRIOR_WEIGHT * league_avg) / (n_played + PRIOR_WEIGHT)
            shrunk_averages[team_key] = (avg_for, avg_against)

        expected_goals = []
        for match in remaining_matches:
            home_key = match["thuis"]
            away_key = match["uit"]

            base_home = (shrunk_averages[home_key][0] * shrunk_averages[away_key][1]) / league_avg
            base_away = (shrunk_averages[away_key][0] * shrunk_averages[home_key][1]) / league_avg

            elo_diff = elo_dict.get(home_key, 1500.0) - elo_dict.get(away_key, 1500.0)
            elo_shift = elo_diff / 400.0

            lambda_home = max(0.2, base_home + elo_shift)
            lambda_away = max(0.2, base_away - elo_shift)
            expected_goals.append((lambda_home, lambda_away))

    else:
        averages = {
            team_key: (
                sum(team_goals_for[team_key]) / len(team_goals_for[team_key])
                if team_goals_for[team_key]
                else fallback_for,
                sum(team_goals_against[team_key]) / len(team_goals_against[team_key])
                if team_goals_against[team_key]
                else fallback_against,
            )
            for team_key in team_names
        }
        expected_goals = [
            (
                max(0.0, (averages[match["thuis"]][0] + averages[match["uit"]][1]) / 2),
                max(0.0, (averages[match["uit"]][0] + averages[match["thuis"]][1]) / 2),
            )
            for match in remaining_matches
        ]

    teams = list(team_names)
    n_teams = len(teams)
    team_indices = {team: index for index, team in enumerate(teams)}
    points = np.zeros((n_simulations, n_teams), dtype=np.int16)
    wins = np.zeros((n_simulations, n_teams), dtype=np.int16)
    goals_for = np.zeros((n_simulations, n_teams), dtype=np.int16)
    goals_against = np.zeros((n_simulations, n_teams), dtype=np.int16)

    max_round = max(all_rounds) if all_rounds else 0
    max_played_round = max(played_rounds) if played_rounds else 0
    round_points_delta = (
        np.zeros((n_simulations, n_teams, max_round + 1), dtype=np.int16)
        if max_round > 0
        else None
    )

    for match in played_matches:
        home_index = team_indices[match["thuis"]]
        away_index = team_indices[match["uit"]]
        home_score = match["score_thuis"]
        away_score = match["score_uit"]
        rnd = match.get("ronde")
        goals_for[:, home_index] += home_score
        goals_against[:, home_index] += away_score
        goals_for[:, away_index] += away_score
        goals_against[:, away_index] += home_score
        if home_score > away_score:
            wins[:, home_index] += 1
            points[:, home_index] += 3
            if round_points_delta is not None and rnd is not None and rnd <= max_round:
                round_points_delta[:, home_index, rnd] += 3
        elif away_score > home_score:
            wins[:, away_index] += 1
            points[:, away_index] += 3
            if round_points_delta is not None and rnd is not None and rnd <= max_round:
                round_points_delta[:, away_index, rnd] += 3
        else:
            points[:, home_index] += 1
            points[:, away_index] += 1
            if round_points_delta is not None and rnd is not None and rnd <= max_round:
                round_points_delta[:, home_index, rnd] += 1
                round_points_delta[:, away_index, rnd] += 1

    rng = np.random.default_rng(_MONTE_CARLO_RANDOM_SEED)
    if remaining_matches:
        home_lambdas = np.array([goals[0] for goals in expected_goals])
        away_lambdas = np.array([goals[1] for goals in expected_goals])
        simulated_home_scores = rng.poisson(
            home_lambdas, size=(n_simulations, len(remaining_matches))
        )
        simulated_away_scores = rng.poisson(
            away_lambdas, size=(n_simulations, len(remaining_matches))
        )

        for match_index, match in enumerate(remaining_matches):
            home_index = team_indices[match["thuis"]]
            away_index = team_indices[match["uit"]]
            rnd = match.get("ronde")
            home_scores = simulated_home_scores[:, match_index]
            away_scores = simulated_away_scores[:, match_index]
            goals_for[:, home_index] += home_scores
            goals_against[:, home_index] += away_scores
            goals_for[:, away_index] += away_scores
            goals_against[:, away_index] += home_scores
            home_wins = home_scores > away_scores
            away_wins = away_scores > home_scores
            wins[:, home_index] += home_wins
            wins[:, away_index] += away_wins
            home_pts = np.where(home_wins, 3, home_scores == away_scores)
            away_pts = np.where(away_wins, 3, home_scores == away_scores)
            points[:, home_index] += home_pts
            points[:, away_index] += away_pts
            if round_points_delta is not None and rnd is not None and rnd <= max_round:
                round_points_delta[:, home_index, rnd] += home_pts
                round_points_delta[:, away_index, rnd] += away_pts

    goal_difference = goals_for - goals_against
    name_order = np.argsort([team_names[team].casefold() for team in teams])
    order = np.lexsort(
        (
            np.broadcast_to(name_order, (n_simulations, n_teams)),
            -goals_for,
            -goal_difference,
            -wins,
            -points,
        ),
        axis=1,
    )
    positions = np.empty_like(order, dtype=np.int16)
    positions[np.arange(n_simulations)[:, None], order] = np.arange(1, n_teams + 1)
    positions_by_team = {
        team: positions[:, index] for team, index in team_indices.items()
    }
    points_by_team = {
        team: points[:, index] for team, index in team_indices.items()
    }

    rows = []
    for team in teams:
        team_pos = positions_by_team[team]
        rows.append(
            {
                "Team": team_names[team],
                "Kampioenschap (%)": (
                    np.count_nonzero(team_pos == 1) / n_simulations * 100
                ),
                "Top 3 (%)": (
                    np.count_nonzero(team_pos <= min(3, n_teams))
                    / n_simulations
                    * 100
                ),
                "Linkerrijtje (%)": (
                    np.count_nonzero(team_pos <= min(6, n_teams))
                    / n_simulations
                    * 100
                ),
                "Degradatiekans (%)": (
                    np.count_nonzero((team_pos == 10) | (team_pos == 11))
                    / n_simulations
                    * 100
                ),
                "Gemiddelde Eindpositie": float(np.mean(team_pos)),
                "Mediaan": float(np.median(team_pos)),
                "10e Percentiel": float(np.percentile(team_pos, 10)),
                "90e Percentiel": float(np.percentile(team_pos, 90)),
                "Verwachte Punten": float(
                    np.mean(points_by_team[team])
                ),
                **{
                    f"Plek {position} (%)": (
                        np.count_nonzero(team_pos == position) / n_simulations * 100
                    )
                    for position in range(1, n_teams + 1)
                },
            }
        )
    summary = pd.DataFrame(
        rows,
        columns=[
            "Team",
            "Kampioenschap (%)",
            "Top 3 (%)",
            "Linkerrijtje (%)",
            "Degradatiekans (%)",
            "Gemiddelde Eindpositie",
            "Mediaan",
            "10e Percentiel",
            "90e Percentiel",
            "Verwachte Punten",
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
        ],
    )
    if not summary.empty:
        summary = summary.sort_values(
            ["Gemiddelde Eindpositie", "Kampioenschap (%)"],
            ascending=[True, False],
            kind="stable",
        ).reset_index(drop=True)

    # Puntenverloop per ronde + positiegrenzen voor alle posities (Plek 1 t/m n_teams)
    trajectory_rows: list[dict[str, Any]] = []
    threshold_rows: list[dict[str, Any]] = []
    if round_points_delta is not None and max_round > 0 and n_teams > 0:
        cum_points = np.cumsum(round_points_delta, axis=2)
        for team_key in teams:
            idx = team_indices[team_key]
            team_label = team_names[team_key]
            for rnd in range(0, max_round + 1):
                arr = cum_points[:, idx, rnd]
                trajectory_rows.append(
                    {
                        "Ronde": rnd,
                        "Team": team_label,
                        "Verwachte_Punten": float(np.mean(arr)),
                        "Mediaan": float(np.median(arr)),
                        "P10": float(np.percentile(arr, 10)),
                        "P90": float(np.percentile(arr, 90)),
                        "Is_Werkelijk": rnd <= max_played_round,
                    }
                )

        for rnd in range(0, max_round + 1):
            sorted_pts = np.sort(cum_points[:, :, rnd], axis=1)[:, ::-1]
            row_thresh: dict[str, Any] = {
                "Ronde": rnd,
                "Is_Werkelijk": rnd <= max_played_round,
            }
            for pos_idx in range(n_teams):
                row_thresh[f"Plek {pos_idx + 1}"] = float(np.mean(sorted_pts[:, pos_idx]))
            threshold_rows.append(row_thresh)

    trajectory_df = pd.DataFrame(
        trajectory_rows,
        columns=[
            "Ronde",
            "Team",
            "Verwachte_Punten",
            "Mediaan",
            "P10",
            "P90",
            "Is_Werkelijk",
        ],
    )
    threshold_cols = ["Ronde", "Is_Werkelijk"] + [f"Plek {i}" for i in range(1, n_teams + 1)]
    thresholds_df = pd.DataFrame(threshold_rows, columns=threshold_cols)

    target_team = _team_key(_ESHG_TEAM)
    target_distribution = (
        pd.DataFrame(
            [
                {
                    "Positie": position,
                    "Kans (%)": (
                        np.count_nonzero(positions_by_team[target_team] == position)
                        / n_simulations
                        * 100
                    ),
                }
                for position in range(1, n_teams + 1)
            ],
            columns=["Positie", "Kans (%)"],
        )
        if target_team in positions_by_team
        else pd.DataFrame(columns=["Positie", "Kans (%)"])
    )
    return summary, {
        "team": _ESHG_TEAM,
        "positie_distributie": target_distribution,
        "punten_verloop": trajectory_df,
        "positie_grenzen": thresholds_df,
        "max_played_round": max_played_round,
        "max_round": max_round,
    }


def calculate_monte_carlo_history(
    matches: list[dict[str, Any]],
    n_simulations: int = 1000,
    model_type: str = "aangepast",
) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    """Bereken hoe ESHG's Monte Carlo-kansen zijn geëvolueerd per gespeelde speelronde."""
    played_rounds = sorted(
        {
            rnd
            for m in matches
            if _valid_played_score(m) is not None and (rnd := _round_int(m.get("ronde"))) is not None
        }
    )
    if not played_rounds:
        return pd.DataFrame(), {}

    history_rows: list[dict[str, Any]] = []
    snapshots_by_round: dict[int, pd.DataFrame] = {}

    for cutoff_round in played_rounds:
        masked_matches: list[dict[str, Any]] = []
        for m in matches:
            rnd = _round_int(m.get("ronde"))
            if _valid_played_score(m) is not None and rnd is not None and rnd <= cutoff_round:
                masked_matches.append(dict(m))
            else:
                masked_matches.append(
                    {
                        **m,
                        "gespeeld": False,
                        "score_thuis": None,
                        "score_uit": None,
                    }
                )

        summary_df, _ = run_monte_carlo_simulation(
            masked_matches,
            n_simulations=n_simulations,
            model_type=model_type,
        )
        snapshots_by_round[cutoff_round] = summary_df

        eshg_rows = summary_df.loc[summary_df["Team"] == _ESHG_TEAM]
        if not eshg_rows.empty:
            row = eshg_rows.iloc[0]
            history_rows.append(
                {
                    "Ronde": cutoff_round,
                    "Kampioenschap (%)": float(row["Kampioenschap (%)"]),
                    "Top 3 (%)": float(row["Top 3 (%)"]),
                    "Linkerrijtje (%)": float(row["Linkerrijtje (%)"]),
                    "Degradatiekans (%)": float(row["Degradatiekans (%)"]),
                    "Verwachte Eindpositie": float(row["Gemiddelde Eindpositie"]),
                    "Verwachte Punten": float(row["Verwachte Punten"]),
                }
            )

    return pd.DataFrame(history_rows), snapshots_by_round


def calculate_next_match_impact(
    matches: list[dict[str, Any]],
    n_simulations: int = 1000,
    model_type: str = "aangepast",
) -> tuple[dict[str, Any] | None, pd.DataFrame]:
    """Bereken hoe Winst, Gelijk of Verlies in het eerstvolgende ESHG-duel de eindkansen beïnvloedt."""
    upcoming_eshg = [
        m
        for m in matches
        if m.get("gespeeld") is False
        and _team_key(_ESHG_TEAM)
        in (_team_key(str(m.get("thuis", ""))), _team_key(str(m.get("uit", ""))))
    ]
    if not upcoming_eshg:
        return None, pd.DataFrame()

    upcoming_eshg.sort(
        key=lambda m: (_round_int(m.get("ronde")) or 999, _normalize_date(m.get("datum")))
    )
    next_match = upcoming_eshg[0]
    is_home = _team_key(str(next_match.get("thuis", ""))) == _team_key(_ESHG_TEAM)
    opponent = str(next_match["uit"] if is_home else next_match["thuis"]).strip()
    rnd = _round_int(next_match.get("ronde"))
    datum = _normalize_date(next_match.get("datum"))

    scenarios = [
        ("Winst ESHG (+3 pt)", (3, 1) if is_home else (1, 3)),
        ("Gelijkspel (+1 pt)", (2, 2)),
        ("Verlies ESHG (+0 pt)", (1, 3) if is_home else (3, 1)),
    ]

    rows: list[dict[str, Any]] = []
    target_id = str(next_match.get("match_id", "")).strip()

    for label, (s_thuis, s_uit) in scenarios:
        modified: list[dict[str, Any]] = []
        applied = False
        for m in matches:
            same_id = target_id and str(m.get("match_id", "")).strip() == target_id
            same_fixture = (
                not target_id
                and m.get("gespeeld") is False
                and _team_key(str(m.get("thuis", ""))) == _team_key(str(next_match.get("thuis", "")))
                and _team_key(str(m.get("uit", ""))) == _team_key(str(next_match.get("uit", "")))
                and _round_int(m.get("ronde")) == rnd
            )
            if not applied and (same_id or same_fixture):
                modified.append(
                    {
                        **m,
                        "gespeeld": True,
                        "score_thuis": s_thuis,
                        "score_uit": s_uit,
                    }
                )
                applied = True
            else:
                modified.append(m)

        summary_df, _ = run_monte_carlo_simulation(
            modified,
            n_simulations=n_simulations,
            model_type=model_type,
        )
        eshg_row = summary_df.loc[summary_df["Team"] == _ESHG_TEAM]
        if not eshg_row.empty:
            r = eshg_row.iloc[0]
            rows.append(
                {
                    "Scenario": label,
                    "Verw. Positie": float(r["Gemiddelde Eindpositie"]),
                    "Verw. Punten": float(r["Verwachte Punten"]),
                    "Kampioenschap (%)": float(r["Kampioenschap (%)"]),
                    "Top 3 (%)": float(r["Top 3 (%)"]),
                    "Linkerrijtje (%)": float(r["Linkerrijtje (%)"]),
                    "Degradatiekans (%)": float(r["Degradatiekans (%)"]),
                }
            )

    meta = {
        "ronde": rnd,
        "datum": datum,
        "tegenstander": opponent,
        "locatie": "Thuis" if is_home else "Uit",
    }
    return meta, pd.DataFrame(rows)


def simulate_standings(simulated_matches: list[dict[str, Any]]) -> pd.DataFrame:
    """Return standings after temporarily applying the simulated match results."""
    matches = get_all_matches()
    current_standings = calculate_standings(matches)
    current_positions = {
        _team_key(str(row["Team"])): int(row["Pos"])
        for _, row in current_standings.iterrows()
    }

    simulation_matches = [
        {**match, "gespeeld": True} for match in simulated_matches
    ]
    virtual_standings = calculate_standings(matches + simulation_matches)
    virtual_standings["Pos_Verschil"] = virtual_standings.apply(
        lambda row: (
            current_positions[_team_key(str(row["Team"]))] - int(row["Pos"])
            if _team_key(str(row["Team"])) in current_positions
            else pd.NA
        ),
        axis=1,
    ).astype("Int64")
    return virtual_standings


def simulate_scenario_horizon(
    matches: list[dict[str, Any]],
    max_round: int,
    fixed_results: list[dict[str, Any]],
    simulate_unplayed: bool = True,
    n_simulations: int = 1000,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Simuleer een scenario t/m `max_round`: deterministisch of met Poisson/ELO-simulatie van overige duels."""
    current_standings = calculate_standings(matches)
    current_positions = {
        _team_key(str(row["Team"])): int(row["Pos"])
        for _, row in current_standings.iterrows()
    }

    if not simulate_unplayed:
        applied = [{**m, "gespeeld": True} for m in fixed_results]
        virtual = calculate_standings(matches + applied)
        virtual["Pos_Verschil"] = virtual.apply(
            lambda row: (
                current_positions[_team_key(str(row["Team"]))] - int(row["Pos"])
                if _team_key(str(row["Team"])) in current_positions
                else pd.NA
            ),
            axis=1,
        ).astype("Int64")
        return virtual, {"mode": "manual", "applied_count": len(applied)}

    fixed_by_id: dict[str, dict[str, Any]] = {}
    fixed_by_tuple: dict[tuple[str, str, int], dict[str, Any]] = {}
    for item in fixed_results:
        mid = str(item.get("match_id", "")).strip()
        if mid:
            fixed_by_id[mid] = item
        rnd = int(item.get("ronde") or 0)
        fixed_by_tuple[(_team_key(str(item.get("thuis", ""))), _team_key(str(item.get("uit", ""))), rnd)] = item

    team_names: dict[str, str] = {}
    played_matches: list[dict[str, Any]] = []
    horizon_simulated_matches: list[dict[str, Any]] = []
    hist_goals_for: dict[str, list[int]] = {}
    hist_goals_against: dict[str, list[int]] = {}

    for match in matches:
        home = str(match.get("thuis", "")).strip()
        away = str(match.get("uit", "")).strip()
        home_key = _team_key(home)
        away_key = _team_key(away)
        if not home_key or not away_key or home_key == away_key:
            continue

        team_names.setdefault(home_key, home)
        team_names.setdefault(away_key, away)
        hist_goals_for.setdefault(home_key, [])
        hist_goals_for.setdefault(away_key, [])
        hist_goals_against.setdefault(home_key, [])
        hist_goals_against.setdefault(away_key, [])

        rnd_val = _round_int(match.get("ronde"))
        rnd = rnd_val if rnd_val is not None else 999

        scores = _valid_played_score(match)
        if scores is not None:
            played_matches.append(
                {
                    "thuis": home_key,
                    "uit": away_key,
                    "score_thuis": scores[0],
                    "score_uit": scores[1],
                }
            )
            hist_goals_for[home_key].append(scores[0])
            hist_goals_against[home_key].append(scores[1])
            hist_goals_for[away_key].append(scores[1])
            hist_goals_against[away_key].append(scores[0])
            continue

        if match.get("gespeeld") is False and rnd <= max_round:
            mid = str(match.get("match_id", "")).strip()
            fixed = fixed_by_id.get(mid) or fixed_by_tuple.get((home_key, away_key, rnd))
            if fixed is not None:
                played_matches.append(
                    {
                        "thuis": home_key,
                        "uit": away_key,
                        "score_thuis": int(fixed["score_thuis"]),
                        "score_uit": int(fixed["score_uit"]),
                    }
                )
            else:
                horizon_simulated_matches.append({"thuis": home_key, "uit": away_key})

    elo_df = calculate_elo_ratings(matches)
    elo_dict = {
        _team_key(str(row["Team"])): float(row["ELO Rating"])
        for _, row in elo_df.iterrows()
    }
    all_goals = [g for goals in hist_goals_for.values() for g in goals]
    league_avg = sum(all_goals) / len(all_goals) if all_goals else 2.5
    prior_weight = 4.0

    shrunk: dict[str, tuple[float, float]] = {}
    for t_key in team_names:
        n_p = len(hist_goals_for[t_key])
        gf = sum(hist_goals_for[t_key])
        ga = sum(hist_goals_against[t_key])
        shrunk[t_key] = (
            (gf + prior_weight * league_avg) / (n_p + prior_weight),
            (ga + prior_weight * league_avg) / (n_p + prior_weight),
        )

    expected_goals: list[tuple[float, float]] = []
    for m in horizon_simulated_matches:
        hk, ak = m["thuis"], m["uit"]
        base_h = (shrunk[hk][0] * shrunk[ak][1]) / league_avg if league_avg > 0 else shrunk[hk][0]
        base_a = (shrunk[ak][0] * shrunk[hk][1]) / league_avg if league_avg > 0 else shrunk[ak][0]
        elo_shift = (elo_dict.get(hk, 1500.0) - elo_dict.get(ak, 1500.0)) / 400.0
        expected_goals.append((max(0.2, base_h + elo_shift), max(0.2, base_a - elo_shift)))

    teams = list(team_names)
    team_indices = {t: idx for idx, t in enumerate(teams)}
    n_teams = len(teams)

    games_played = np.zeros((n_simulations, n_teams), dtype=np.int16)
    points = np.zeros((n_simulations, n_teams), dtype=np.int16)
    wins = np.zeros((n_simulations, n_teams), dtype=np.int16)
    goals_for = np.zeros((n_simulations, n_teams), dtype=np.int16)
    goals_against = np.zeros((n_simulations, n_teams), dtype=np.int16)

    for m in played_matches:
        hi = team_indices[m["thuis"]]
        ai = team_indices[m["uit"]]
        hs, as_ = m["score_thuis"], m["score_uit"]
        games_played[:, hi] += 1
        games_played[:, ai] += 1
        goals_for[:, hi] += hs
        goals_against[:, hi] += as_
        goals_for[:, ai] += as_
        goals_against[:, ai] += hs
        if hs > as_:
            wins[:, hi] += 1
            points[:, hi] += 3
        elif as_ > hs:
            wins[:, ai] += 1
            points[:, ai] += 3
        else:
            points[:, hi] += 1
            points[:, ai] += 1

    rng = np.random.default_rng(_MONTE_CARLO_RANDOM_SEED)
    if horizon_simulated_matches:
        h_lambdas = np.array([g[0] for g in expected_goals])
        a_lambdas = np.array([g[1] for g in expected_goals])
        sim_h = rng.poisson(h_lambdas, size=(n_simulations, len(horizon_simulated_matches)))
        sim_a = rng.poisson(a_lambdas, size=(n_simulations, len(horizon_simulated_matches)))

        for idx, m in enumerate(horizon_simulated_matches):
            hi = team_indices[m["thuis"]]
            ai = team_indices[m["uit"]]
            hs = sim_h[:, idx]
            as_ = sim_a[:, idx]
            games_played[:, hi] += 1
            games_played[:, ai] += 1
            goals_for[:, hi] += hs
            goals_against[:, hi] += as_
            goals_for[:, ai] += as_
            goals_against[:, ai] += hs
            hw = hs > as_
            aw = as_ > hs
            wins[:, hi] += hw
            wins[:, ai] += aw
            points[:, hi] += np.where(hw, 3, hs == as_)
            points[:, ai] += np.where(aw, 3, hs == as_)

    goal_diff = goals_for - goals_against
    name_order = np.argsort([team_names[t].casefold() for t in teams])
    order = np.lexsort(
        (
            np.broadcast_to(name_order, (n_simulations, n_teams)),
            -goals_for,
            -goal_diff,
            -wins,
            -points,
        ),
        axis=1,
    )
    positions = np.empty_like(order, dtype=np.int16)
    positions[np.arange(n_simulations)[:, None], order] = np.arange(1, n_teams + 1)

    rows = []
    eshg_meta: dict[str, Any] = {}
    for t_key in teams:
        idx = team_indices[t_key]
        pos_arr = positions[:, idx]
        pts_arr = points[:, idx]
        gs_val = int(games_played[0, idx])
        p10 = int(round(float(np.percentile(pos_arr, 10))))
        p90 = int(round(float(np.percentile(pos_arr, 90))))
        avg_pos = float(np.mean(pos_arr))
        avg_pts = float(np.mean(pts_arr))
        top3_pct = float(np.count_nonzero(pos_arr <= min(3, n_teams)) / n_simulations * 100)
        left_pct = float(np.count_nonzero(pos_arr <= min(6, n_teams)) / n_simulations * 100)

        row_dict = {
            "Verw. Pos": round(avg_pos, 1),
            "Huidig": current_positions.get(t_key, pd.NA),
            "Team": team_names[t_key],
            "GS": gs_val,
            "Verw. PT": round(avg_pts, 1),
            "Bandbreedte": f"{p10}e – {p90}e" if p10 != p90 else f"{p10}e",
            "Top 3 (%)": round(top3_pct, 1),
            "Linkerrijtje (%)": round(left_pct, 1),
        }
        rows.append(row_dict)
        if t_key == _team_key(_ESHG_TEAM):
            eshg_meta = {
                "huidig": current_positions.get(t_key),
                "verw_pos": avg_pos,
                "verw_pt": avg_pts,
                "p10": p10,
                "p90": p90,
                "top3_pct": top3_pct,
                "left_pct": left_pct,
            }

    summary = pd.DataFrame(rows).sort_values(
        ["Verw. Pos", "Verw. PT"],
        ascending=[True, False],
        kind="stable",
    ).reset_index(drop=True)

    return summary, {
        "mode": "simulated",
        "simulated_other_count": len(horizon_simulated_matches),
        "eshg": eshg_meta,
    }


def get_quarter_stats() -> pd.DataFrame:
    """Return ESHG and opponent goals aggregated by quarter, including match coverage in attrs."""
    quarter_goals = {
        f"Q{quarter}": {"Goals ESHG": 0, "Goals Tegen": 0}
        for quarter in range(1, 5)
    }

    scoring_matches = [
        match for match in _get_scoring_matches() if _match_has_result(match)
    ]
    tracked_matches = 0

    for match in scoring_matches:
        if match.get("kwarten_bijgehouden") is False:
            continue
        quarters = match.get("kwarten")
        if not isinstance(quarters, dict):
            continue

        eshg_quarters = quarters.get("eshg")
        opponent_quarters = quarters.get("tegenstander")
        if not isinstance(eshg_quarters, list) or not isinstance(
            opponent_quarters, list
        ):
            continue
        if len(eshg_quarters) != 4 or len(opponent_quarters) != 4:
            continue

        tracked_matches += 1
        for quarter_index in range(4):
            eshg_score = _score(
                eshg_quarters[quarter_index]
                if quarter_index < len(eshg_quarters)
                else None
            )
            opponent_score = _score(
                opponent_quarters[quarter_index]
                if quarter_index < len(opponent_quarters)
                else None
            )
            if eshg_score is not None:
                quarter_goals[f"Q{quarter_index + 1}"]["Goals ESHG"] += eshg_score
            if opponent_score is not None:
                quarter_goals[f"Q{quarter_index + 1}"]["Goals Tegen"] += opponent_score

    rows = []
    for quarter, totals in quarter_goals.items():
        rows.append(
            {
                "Kwart": quarter,
                **totals,
                "Doelsaldo": totals["Goals ESHG"] - totals["Goals Tegen"],
            }
        )
    frame = pd.DataFrame(
        rows,
        columns=["Kwart", "Goals ESHG", "Goals Tegen", "Doelsaldo"],
    )
    frame.attrs["wedstrijden_bijgehouden"] = tracked_matches
    frame.attrs["wedstrijden_totaal"] = len(scoring_matches)
    return frame


def get_corner_stats() -> dict[str, int | float]:
    """Return attacking and defensive penalty-corner totals, percentages, and match coverage."""
    scoring_matches = [
        match for match in _get_scoring_matches() if _match_has_result(match)
    ]
    tracked_matches = 0

    stats: dict[str, int | float] = {
        "voor_totaal": 0,
        "voor_gescoord": 0,
        "conversie_percentage": 0.0,
        "tegen_totaal": 0,
        "tegen_gescoord": 0,
        "verdedigingspercentage": 0.0,
        "wedstrijden_bijgehouden": 0,
        "wedstrijden_totaal": len(scoring_matches),
    }

    for match in scoring_matches:
        if match.get("corners_bijgehouden") is False:
            continue
        corners = match.get("corners")
        if not isinstance(corners, dict):
            continue

        tracked_matches += 1
        for field in ("voor_totaal", "voor_gescoord", "tegen_totaal", "tegen_gescoord"):
            value = _score(corners.get(field))
            if value is not None:
                stats[field] += value

    stats["wedstrijden_bijgehouden"] = tracked_matches
    if stats["voor_totaal"]:
        stats["conversie_percentage"] = (
            stats["voor_gescoord"] / stats["voor_totaal"] * 100
        )
    if stats["tegen_totaal"]:
        stats["verdedigingspercentage"] = (
            1 - stats["tegen_gescoord"] / stats["tegen_totaal"]
        ) * 100
    return stats


def get_goal_type_distribution() -> pd.DataFrame:
    """Count ESHG goals by type across recorded matches."""
    goal_types = {
        "Veldgoal": 0,
        "Strafcorner": 0,
        "Strafbal (PS)": 0,
    }
    for match in _get_scoring_matches():
        if not _match_has_result(match):
            continue
        for goal in _goal_records(match):
            goal_type = _person_name(goal.get("type"))
            if goal_type == "Strafbal":
                goal_type = "Strafbal (PS)"
            if goal_type in goal_types:
                goal_types[goal_type] += 1

    return pd.DataFrame(
        [
            {"Type": goal_type, "Aantal": count}
            for goal_type, count in goal_types.items()
        ],
        columns=["Type", "Aantal"],
    )


def get_pitchers() -> list[dict[str, Any]]:
    """Laad alle geregistreerde pitchers uit data/pitchers.json."""
    return _load_json_records(_PITCHERS_FILE)


def _save_pitchers(records: list[dict[str, Any]]) -> None:
    try:
        _PITCHERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _PITCHERS_FILE.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2)
            file.write("\n")
    except OSError as error:
        raise ValueError(f"Pitchers konden niet worden opgeslagen: {error}") from error


def add_pitcher_record(speler: str, datum: str, aantal: int, reden: str) -> None:
    """Voeg een nieuw openstaand pitcher-item toe."""
    records = get_pitchers()
    records.append(
        {
            "id": f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{len(records)}",
            "speler": speler.strip(),
            "datum": _normalize_date(datum),
            "aantal": max(1, int(aantal)),
            "reden": reden.strip() or "Geen reden opgegeven",
            "gehaald": False,
            "gehaald_op": None,
        }
    )
    _save_pitchers(records)


def set_pitcher_collected(pitcher_id: str, collected: bool) -> None:
    """Markeer een pitcher-item als geïnd/gehaald of zet terug naar openstaand."""
    records = get_pitchers()
    today_str = datetime.now().date().isoformat()
    for item in records:
        if item.get("id") == pitcher_id:
            item["gehaald"] = bool(collected)
            item["gehaald_op"] = today_str if collected else None
            break
    _save_pitchers(records)


def delete_pitcher_record(pitcher_id: str) -> None:
    """Verwijder een pitcher-item definitief."""
    records = [item for item in get_pitchers() if item.get("id") != pitcher_id]
    _save_pitchers(records)