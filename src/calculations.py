import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.constants import PLAYERS


_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_POULE_FILE = _DATA_DIR / "poule_matches.json"
_MATCH_FILES = (_DATA_DIR / "matches.json", _DATA_DIR / "wedstrijden.json")
_ESHG_TEAM = "Don Quishoot H3"
_OWN_GOAL_LABEL = "Eigen doelpunt tegenstander"
_PLAYER_STAT_COLUMNS = [
    "Positie",
    "Speler",
    "Goals",
    "Veldgoals",
    "Strafcorners",
    "Strafballen",
    "Assists",
    "Totaal_G_A",
]


def _load_json_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        with path.open("r", encoding="utf-8") as file:
            records = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Wedstrijdenbestand kan niet worden gelezen ({path}): {error}") from error

    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise ValueError(f"Wedstrijdenbestand moet een lijst met objecten bevatten: {path}")
    return records


def _get_scoring_matches() -> list[dict[str, Any]]:
    """Load scoring matches, preferring matches.json for duplicate match IDs."""
    matches_by_id: dict[str, dict[str, Any]] = {}
    matches_without_id: list[dict[str, Any]] = []
    for path in reversed(_MATCH_FILES):
        for index, match in enumerate(_load_json_records(path)):
            match_id = str(match.get("match_id", "")).strip()
            if match_id:
                matches_by_id[match_id] = match
            else:
                matches_without_id.append(match)
    matches = [*matches_without_id, *matches_by_id.values()]
    completed_matches = []
    for match in matches:
        if match.get("gespeeld") is False:
            continue
        match_date = _normalize_date(match.get("datum"))
        try:
            if match_date and date.fromisoformat(match_date) > date.today():
                continue
        except ValueError:
            continue
        completed_matches.append(match)
    return completed_matches


def _goal_records(match: dict[str, Any]) -> list[dict[str, Any]]:
    goals = match.get("goals")
    if not isinstance(goals, list):
        return []
    return [goal for goal in goals if isinstance(goal, dict)]


def _person_name(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _empty_player_stats() -> dict[str, int]:
    return {
        "Goals": 0,
        "Veldgoals": 0,
        "Strafcorners": 0,
        "Strafballen": 0,
        "Assists": 0,
    }


def calculate_player_stats() -> pd.DataFrame:
    """Calculate goal and assist statistics for the squad and recorded players."""
    player_names = [player for player in PLAYERS if player != _OWN_GOAL_LABEL]
    stats: dict[str, dict[str, int]] = {
        player: _empty_player_stats() for player in player_names
    }

    for match in _get_scoring_matches():
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

    rows = [
        {
            "Speler": player,
            **player_stats,
            "Totaal_G_A": player_stats["Goals"] + player_stats["Assists"],
        }
        for player, player_stats in stats.items()
    ]

    frame = pd.DataFrame(rows)
    frame = frame.sort_values(
        ["Goals", "Assists", "Totaal_G_A"],
        ascending=[False, False, False],
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
    """Return matches where a player scored or provided an assist."""
    timeline: list[dict[str, str | int]] = []
    for match in _get_scoring_matches():
        goals = _goal_records(match)
        player_goals = sum(
            _person_name(goal.get("maker")) == player for goal in goals
        )
        player_assists = sum(
            _person_name(goal.get("assist")) == player for goal in goals
        )
        if not player_goals and not player_assists:
            continue

        opponent = _person_name(match.get("tegenstander"))
        if not opponent:
            opponent = (
                f"{_person_name(match.get('thuis'))} - "
                f"{_person_name(match.get('uit'))}"
            ).strip(" -")
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
                "Bijdrage": " + ".join(involvement),
                "Goals": player_goals,
                "Assists": player_assists,
            }
        )

    timeline.sort(key=lambda row: str(row["Datum"]), reverse=True)
    return pd.DataFrame(
        timeline,
        columns=["Datum", "Tegenstander", "Bijdrage", "Goals", "Assists"],
    )


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
    try:
        score = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if score < 0:
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    return score


def _fixture_key(match: dict[str, Any]) -> tuple[str, str, str]:
    teams = sorted((_team_key(match["thuis"]), _team_key(match["uit"])))
    return _normalize_date(match["datum"]), teams[0], teams[1]


def _local_result(record: dict[str, Any]) -> tuple[str, str, int, int] | None:
    """Return date, opponent, ESHG score, and opponent score for a local match."""
    match_date = _normalize_date(record.get("datum"))
    if not match_date:
        return None
    try:
        if date.fromisoformat(match_date) > date.today():
            return None
    except ValueError:
        return None
    if record.get("gespeeld") is False:
        return None

    home = str(record.get("thuis", "")).strip()
    away = str(record.get("uit", "")).strip()
    if home and away:
        if _team_key(home) == _team_key(_ESHG_TEAM):
            opponent = away
            home_score = _score(record.get("score_thuis"))
            away_score = _score(record.get("score_uit"))
            if home_score is not None and away_score is not None:
                return match_date, opponent, home_score, away_score
        elif _team_key(away) == _team_key(_ESHG_TEAM):
            opponent = home
            home_score = _score(record.get("score_thuis"))
            away_score = _score(record.get("score_uit"))
            if home_score is not None and away_score is not None:
                return match_date, opponent, away_score, home_score
        return None

    opponent = str(record.get("tegenstander", "")).strip()
    if not opponent:
        return None

    score_data = record.get("score")
    score_data = score_data if isinstance(score_data, dict) else {}
    eshg_score = _score(score_data.get("eshg", record.get("score_eshg")))
    opponent_score = _score(
        score_data.get("tegenstander", record.get("score_tegenstander"))
    )
    if eshg_score is None or opponent_score is None:
        return None
    return match_date, opponent, eshg_score, opponent_score


def _standardize_poule_match(record: dict[str, Any]) -> dict[str, Any] | None:
    match_date = _normalize_date(record.get("datum"))
    home = str(record.get("thuis", "")).strip()
    away = str(record.get("uit", "")).strip()
    if not match_date or not home or not away:
        return None

    home_score = _score(record.get("score_thuis"))
    away_score = _score(record.get("score_uit"))
    try:
        date_is_past_or_today = date.fromisoformat(match_date) <= date.today()
    except ValueError:
        date_is_past_or_today = False
    played = (
        record.get("gespeeld") is True
        and date_is_past_or_today
        and home_score is not None
        and away_score is not None
    )
    match = {
        "datum": match_date,
        "thuis": home,
        "uit": away,
        "score_thuis": home_score if played else None,
        "score_uit": away_score if played else None,
        "gespeeld": played,
    }
    if "ronde" in record:
        match["ronde"] = record["ronde"]
    return match


def get_all_matches() -> list[dict]:
    """Load and merge scheduled pool fixtures with ESHG match results."""
    poule_records = _load_json_records(_POULE_FILE)
    matches_by_fixture: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in poule_records:
        match = _standardize_poule_match(record)
        if match is None:
            continue

        fixture_key = _fixture_key(match)
        previous = matches_by_fixture.get(fixture_key)
        if previous is None or (
            not previous["gespeeld"] and match["gespeeld"]
        ):
            matches_by_fixture[fixture_key] = match

    local_results: dict[tuple[str, str], tuple[int, int]] = {}
    local_fixtures: dict[tuple[str, str, str], dict[str, Any]] = {}
    # Prefer matches.json over the legacy wedstrijden.json when both contain a fixture.
    for path in reversed(_MATCH_FILES):
        for record in _load_json_records(path):
            result = _local_result(record)
            if result is None:
                continue
            match_date, opponent, eshg_score, opponent_score = result
            local_results[(match_date, _team_key(opponent))] = (
                eshg_score,
                opponent_score,
            )

            location = str(record.get("locatie", "")).strip().casefold()
            if location == "uit":
                home, away = opponent, _ESHG_TEAM
                home_score, away_score = opponent_score, eshg_score
            elif location == "thuis":
                home, away = _ESHG_TEAM, opponent
                home_score, away_score = eshg_score, opponent_score
            else:
                # If location is not stored, use the matching scheduled fixture's orientation.
                scheduled = matches_by_fixture.get(
                    (
                        match_date,
                        *sorted((_team_key(_ESHG_TEAM), _team_key(opponent))),
                    )
                )
                if scheduled and _team_key(scheduled["thuis"]) == _team_key(_ESHG_TEAM):
                    home, away = _ESHG_TEAM, opponent
                    home_score, away_score = eshg_score, opponent_score
                else:
                    home, away = opponent, _ESHG_TEAM
                    home_score, away_score = opponent_score, eshg_score

            local_match = {
                "datum": match_date,
                "thuis": home,
                "uit": away,
                "score_thuis": home_score,
                "score_uit": away_score,
                "gespeeld": True,
            }
            local_fixtures[_fixture_key(local_match)] = local_match

    for fixture_key, match in matches_by_fixture.items():
        if _team_key(_ESHG_TEAM) not in (
            _team_key(match["thuis"]),
            _team_key(match["uit"]),
        ):
            continue
        opponent = (
            match["uit"]
            if _team_key(match["thuis"]) == _team_key(_ESHG_TEAM)
            else match["thuis"]
        )
        result = local_results.get(
            (_normalize_date(match["datum"]), _team_key(opponent))
        )
        if result is None:
            continue

        eshg_score, opponent_score = result
        if _team_key(match["thuis"]) == _team_key(_ESHG_TEAM):
            match["score_thuis"], match["score_uit"] = eshg_score, opponent_score
        else:
            match["score_thuis"], match["score_uit"] = opponent_score, eshg_score
        match["gespeeld"] = True

    for fixture_key, local_match in local_fixtures.items():
        matches_by_fixture.setdefault(fixture_key, local_match)

    return list(matches_by_fixture.values())


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


def _valid_played_score(match: dict) -> tuple[int, int] | None:
    if match.get("gespeeld") is not True:
        return None
    home_score = _score(match.get("score_thuis"))
    away_score = _score(match.get("score_uit"))
    if home_score is None or away_score is None:
        return None
    return home_score, away_score


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
    }


def _local_match_details() -> dict[tuple[str, str], dict[str, Any]]:
    details: dict[tuple[str, str], dict[str, Any]] = {}
    # matches.json takes precedence over the legacy wedstrijden.json.
    for path in reversed(_MATCH_FILES):
        for record in _load_json_records(path):
            result = _local_result(record)
            if result is None:
                continue
            match_date, opponent, _, _ = result
            details[(match_date, _team_key(opponent))] = {
                "notities": (
                    record.get("notities")
                    if isinstance(record.get("notities"), dict)
                    else {}
                ),
                "extra_stats": (
                    record.get("extra_stats")
                    if isinstance(record.get("extra_stats"), dict)
                    else {}
                ),
            }
    return details


def get_head_to_head(opponent: str) -> dict[str, Any]:
    """Return ESHG's played results and saved notes against an opponent."""
    opponent_key = _team_key(opponent)
    match_details = _local_match_details()
    meetings: list[dict[str, Any]] = []

    for match in get_all_matches():
        eshg_result = _team_match_result(match, _ESHG_TEAM)
        if eshg_result is None or _team_key(eshg_result["tegenstander"]) != opponent_key:
            continue

        details = match_details.get(
            (eshg_result["datum"], opponent_key), {}
        )
        meetings.append({**eshg_result, **details})

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


def calculate_standings(matches: list[dict]) -> pd.DataFrame:
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
        home_standing["GS"] += 1
        away_standing["GS"] += 1
        home_standing["DV"] += home_score
        home_standing["DT"] += away_score
        away_standing["DV"] += away_score
        away_standing["DT"] += home_score

        if home_score > away_score:
            home_standing["W"] += 1
            home_standing["PT"] += 3
            away_standing["V"] += 1
        elif home_score < away_score:
            away_standing["W"] += 1
            away_standing["PT"] += 3
            home_standing["V"] += 1
        else:
            home_standing["G"] += 1
            home_standing["PT"] += 1
            away_standing["G"] += 1
            away_standing["PT"] += 1

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


def calculate_elo_ratings(
    matches: list[dict], k_factor: int = 32, start_elo: float = 1500.0
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


def run_monte_carlo_simulation(
    matches: list[dict], n_simulations: int = 1000
) -> tuple[pd.DataFrame, dict]:
    """Simulate the remaining pool fixtures and summarize final standings."""
    if n_simulations <= 0:
        raise ValueError("n_simulations moet groter zijn dan nul.")

    team_names: dict[str, str] = {}
    played_matches: list[dict[str, Any]] = []
    remaining_matches: list[dict[str, Any]] = []
    team_goals_for: dict[str, list[int]] = {}
    team_goals_against: dict[str, list[int]] = {}

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

        scores = _valid_played_score(match)
        if scores is not None:
            home_score, away_score = scores
            played_matches.append(
                {
                    "thuis": home_key,
                    "uit": away_key,
                    "score_thuis": home_score,
                    "score_uit": away_score,
                }
            )
            team_goals_for[home_key].append(home_score)
            team_goals_against[home_key].append(away_score)
            team_goals_for[away_key].append(away_score)
            team_goals_against[away_key].append(home_score)
        elif match.get("gespeeld") is False:
            remaining_matches.append({"thuis": home_key, "uit": away_key})

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
    points_by_team = {team: np.zeros(n_simulations) for team in teams}
    positions_by_team = {team: np.zeros(n_simulations, dtype=int) for team in teams}

    for simulation_index in range(n_simulations):
        standings: dict[str, dict[str, int]] = {
            team: {"W": 0, "PT": 0, "DV": 0, "DT": 0} for team in teams
        }
        for match in played_matches:
            home_score = match["score_thuis"]
            away_score = match["score_uit"]
            home_row = standings[match["thuis"]]
            away_row = standings[match["uit"]]
            home_row["DV"] += home_score
            home_row["DT"] += away_score
            away_row["DV"] += away_score
            away_row["DT"] += home_score
            if home_score > away_score:
                home_row["W"] += 1
                home_row["PT"] += 3
            elif away_score > home_score:
                away_row["W"] += 1
                away_row["PT"] += 3
            else:
                home_row["PT"] += 1
                away_row["PT"] += 1

        for match, (home_lambda, away_lambda) in zip(
            remaining_matches, expected_goals
        ):
            home_score = int(np.random.poisson(lam=home_lambda))
            away_score = int(np.random.poisson(lam=away_lambda))
            home_row = standings[match["thuis"]]
            away_row = standings[match["uit"]]
            home_row["DV"] += home_score
            home_row["DT"] += away_score
            away_row["DV"] += away_score
            away_row["DT"] += home_score
            if home_score > away_score:
                home_row["W"] += 1
                home_row["PT"] += 3
            elif away_score > home_score:
                away_row["W"] += 1
                away_row["PT"] += 3
            else:
                home_row["PT"] += 1
                away_row["PT"] += 1

        ordered_teams = sorted(
            teams,
            key=lambda team: (
                -standings[team]["PT"],
                -standings[team]["W"],
                -(standings[team]["DV"] - standings[team]["DT"]),
                -standings[team]["DV"],
                team_names[team].casefold(),
            ),
        )
        for position, team in enumerate(ordered_teams, start=1):
            positions_by_team[team][simulation_index] = position
            points_by_team[team][simulation_index] = standings[team]["PT"]

    n_teams = len(teams)
    rows = []
    for team in teams:
        positions = positions_by_team[team]
        rows.append(
            {
                "Team": team_names[team],
                "Kans op Kampioenschap (%)": (
                    np.count_nonzero(positions == 1) / n_simulations * 100
                ),
                "Kans op Top 3 (%)": (
                    np.count_nonzero(positions <= min(3, n_teams))
                    / n_simulations
                    * 100
                ),
                "Kans op Degradatiezone (%)": (
                    np.count_nonzero((positions == 10) | (positions == 11))
                    / n_simulations
                    * 100
                ),
                "Verwachte Eindpositie (gemiddeld)": float(np.mean(positions)),
                "Verwachte Eindpositie (mediaan)": float(np.median(positions)),
                "Verwachte Punten (gemiddeld)": float(
                    np.mean(points_by_team[team])
                ),
                **{
                    f"Plek {position} (%)": (
                        np.count_nonzero(positions == position) / n_simulations * 100
                    )
                    for position in range(1, n_teams + 1)
                }

            }
        )
    summary = pd.DataFrame(
        rows,
        columns=[
            "Team",
            "Kans op Kampioenschap (%)",
            "Kans op Top 3 (%)",
            "Kans op Degradatiezone (%)",
            "Verwachte Eindpositie (gemiddeld)",
            "Verwachte Eindpositie (mediaan)",
            "Verwachte Punten (gemiddeld)",
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
            ["Kans op Kampioenschap (%)", "Verwachte Eindpositie (gemiddeld)"],
            ascending=[False, True],
            kind="stable",
        ).reset_index(drop=True)

    target_team = _team_key(_ESHG_TEAM)
    target_distribution = pd.DataFrame(
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
    ) if target_team in positions_by_team else pd.DataFrame(
        columns=["Positie", "Kans (%)"]
    )
    return summary, {
        "team": _ESHG_TEAM,
        "positie_distributie": target_distribution,
    }


def simulate_standings(simulated_matches: list[dict]) -> pd.DataFrame:
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


def _match_has_result(match: dict[str, Any]) -> bool:
    score = match.get("score")
    if not isinstance(score, dict):
        return False
    return (
        _score(score.get("eshg")) is not None
        and _score(score.get("tegenstander")) is not None
    )


def get_quarter_stats() -> pd.DataFrame:
    """Return ESHG and opponent goals aggregated by quarter."""
    quarter_goals = {
        f"Q{quarter}": {"Goals ESHG": 0, "Goals Tegen": 0}
        for quarter in range(1, 5)
    }

    for match in _get_scoring_matches():
        if not _match_has_result(match):
            continue
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
    return pd.DataFrame(
        rows,
        columns=["Kwart", "Goals ESHG", "Goals Tegen", "Doelsaldo"],
    )


def get_corner_stats() -> dict[str, int | float]:
    """Return attacking and defensive penalty-corner totals and percentages."""
    stats = {
        "voor_totaal": 0,
        "voor_gescoord": 0,
        "conversie_percentage": 0.0,
        "tegen_totaal": 0,
        "tegen_gescoord": 0,
        "verdedigingspercentage": 0.0,
    }

    for match in _get_scoring_matches():
        if not _match_has_result(match):
            continue
        if match.get("corners_bijgehouden") is False:
            continue
        corners = match.get("corners")
        if not isinstance(corners, dict):
            continue

        for field in ("voor_totaal", "voor_gescoord", "tegen_totaal", "tegen_gescoord"):
            value = _score(corners.get(field))
            if value is not None:
                stats[field] += value

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
