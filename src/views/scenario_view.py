from typing import Any, cast

import pandas as pd
import streamlit as st  # type: ignore[import-not-found]

from src.calculations import get_all_matches, simulate_scenario_horizon


_ESHG_TEAM = "Don Quishoot H3"
_MANUAL_DISPLAY_COLUMNS = ["Pos", "Verschil", "Team", "GS", "PT", "W", "G", "V", "DS"]


def _round_number(match: dict[str, Any]) -> int | None:
    value = match.get("ronde")
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        round_number = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round_number if round_number > 0 else None


def _is_eshg_match(match: dict[str, Any]) -> bool:
    return _ESHG_TEAM in (str(match.get("thuis", "")).strip(), str(match.get("uit", "")).strip())


def _difference_label(value: object) -> str:
    scalar_value = cast(Any, value)
    if pd.isna(scalar_value):
        return "—"
    difference = int(scalar_value)
    if difference > 0:
        return f"🟢 ▲ {difference}"
    if difference < 0:
        return f"🔴 ▼ {abs(difference)}"
    return "⚪ ="


def _highlight_eshg(row: pd.Series) -> list[str]:
    if row["Team"] == _ESHG_TEAM:
        return ["background-color: rgba(46, 125, 50, 0.25); font-weight: bold"] * len(row)
    return [""] * len(row)


def _scores_from_outcome(outcome: str) -> tuple[int, int]:
    """Zet W/G/V om naar een standaard doelsaldo (+2 / 0 / -2)."""
    if outcome == "home":
        return 3, 1
    if outcome == "away":
        return 1, 3
    return 2, 2


def _render_manual_conclusion(
    standings: pd.DataFrame,
    simulated_matches: list[dict[str, Any]],
) -> None:
    eshg_row = standings.loc[standings["Team"] == _ESHG_TEAM]
    if eshg_row.empty:
        st.info("Don Quishoot H3 staat nog niet in de berekende ranglijst.")
        return

    row = eshg_row.iloc[0]
    current_position = (
        int(row["Pos"]) + int(row["Pos_Verschil"])
        if not pd.isna(row["Pos_Verschil"])
        else None
    )
    new_position = int(row["Pos"])
    difference = (
        int(row["Pos_Verschil"]) if not pd.isna(row["Pos_Verschil"]) else None
    )
    if current_position is None:
        st.info(f"Don Quishoot H3 komt virtueel uit op plek {new_position}.")
        return

    eshg_sim_count = sum(1 for m in simulated_matches if _is_eshg_match(m))
    if difference is None:
        conclusion = f"Don Quishoot H3 komt uit op plek {new_position} ({int(row['PT'])} pt)."
    elif difference > 0:
        conclusion = (
            f"Don Quishoot H3 stijgt van plek {current_position} naar plek "
            f"**{new_position}** ({difference:+d}) met **{int(row['PT'])} punten**."
        )
    elif difference < 0:
        conclusion = (
            f"Don Quishoot H3 daalt van plek {current_position} naar plek "
            f"**{new_position}** ({difference:+d}) met **{int(row['PT'])} punten**."
        )
    else:
        conclusion = (
            f"Don Quishoot H3 blijft op plek **{new_position}** met **{int(row['PT'])} punten**."
        )

    if eshg_sim_count > 1:
        conclusion += f" *(Gebaseerd op {eshg_sim_count} ingevulde ESHG-wedstrijden.)*"

    passed_teams = standings.loc[
        (standings["Pos"] > new_position)
        & (standings["Pos_Verschil"].notna())
        & (standings["Pos"] + standings["Pos_Verschil"] < current_position)
    ]
    if not passed_teams.empty:
        passed_team = passed_teams.iloc[0]
        reason = (
            " op doelsaldo"
            if (
                int(row["PT"]) == int(passed_team["PT"])
                and int(row["W"]) == int(passed_team["W"])
                and int(row["DS"]) != int(passed_team["DS"])
            )
            else ""
        )
        conclusion += f" Het passeert **{passed_team['Team']}**{reason}."
    st.markdown(conclusion)


def render_scenario_view() -> None:
    st.title("🔮 Scenario Calculator")

    try:
        matches = get_all_matches()
    except ValueError as error:
        st.error(f"Het wedstrijdprogramma kon niet worden geladen: {error}")
        return

    planned_matches = [
        match for match in matches if match.get("gespeeld") is False
    ]
    if not planned_matches:
        st.info("Er zijn geen geplande wedstrijden om te simuleren.")
        return

    all_unplayed_rounds = sorted(
        {
            rnd
            for m in planned_matches
            if (rnd := _round_number(m)) is not None
        }
    )
    if not all_unplayed_rounds:
        st.info("Er zijn geen geplande wedstrijden met een geldig rondenummer.")
        return

    eshg_unplayed_rounds = sorted(
        {
            rnd
            for m in planned_matches
            if _is_eshg_match(m) and (rnd := _round_number(m)) is not None
        }
    )
    first_eshg_round = eshg_unplayed_rounds[0] if eshg_unplayed_rounds else all_unplayed_rounds[0]
    target_round_options = [r for r in all_unplayed_rounds if r >= first_eshg_round] or all_unplayed_rounds

    col_round, col_mode = st.columns([1.2, 2.2])
    with col_round:
        target_round = st.selectbox(
            "Simuleer t/m speelronde",
            options=target_round_options,
            index=0,
            key="scenario_target_round",
            help="Kies tot en met welke speelronde je vooruit wilt kijken. Eventuele inhaalwedstrijden uit eerdere rondes worden automatisch meegenomen.",
        )

    with col_mode:
        mode = st.radio(
            "Simulatiemodus",
            [
                "Alleen ESHG invullen (rest simuleren)",
                "Handmatig scenario (meerdere rondes)",
            ],
            index=0,
            horizontal=True,
            key="scenario_mode",
        )

    horizon_matches = [
        m
        for m in planned_matches
        if (rnd := _round_number(m)) is not None and rnd <= target_round
    ]
    horizon_matches.sort(key=lambda m: (_round_number(m) or 999, str(m.get("datum", ""))))

    catchup_matches = [
        m
        for m in horizon_matches
        if (_round_number(m) or 999) < first_eshg_round and not _is_eshg_match(m)
    ]
    if catchup_matches:
        catchup_labels = ", ".join(
            f"{m['thuis']} – {m['uit']} (ronde {_round_number(m)})" for m in catchup_matches
        )
        st.caption(
            f"ℹ️ Inclusief nog niet gespeelde inhaalwedstrijd(en) uit eerdere ronde: {catchup_labels}."
        )

    fixed_results: list[dict[str, Any]] = []

    # =========================================================================
    # MODUS A: ALLEEN ESHG INVULLEN (REST AUTOMATISCH SIMULEREN)
    # =========================================================================
    if mode == "Alleen ESHG invullen (rest simuleren)":
        eshg_horizon = [m for m in horizon_matches if _is_eshg_match(m)]
        use_exact = st.checkbox(
            "Exacte uitslagen invullen (voor doelsaldo)",
            value=False,
            key="scenario_exact_eshg",
        )
        if not use_exact:
            st.caption(
                "Zonder exacte uitslag rekent Winst/Gelijk/Verlies met een standaard doelsaldo van +2 / 0 / -2. "
                "Overige poulewedstrijden t/m ronde "
                f"{target_round} worden 1.000× gesimuleerd op basis van ELO en aanval/verdediging."
            )

        if not eshg_horizon:
            st.info(f"Don Quishoot H3 heeft geen geplande wedstrijden t/m speelronde {target_round}.")
        else:
            for idx, match in enumerate(eshg_horizon):
                rnd = _round_number(match)
                is_home = str(match.get("thuis", "")).strip() == _ESHG_TEAM
                opponent = str(match["uit"] if is_home else match["thuis"]).strip()
                loc_tag = "Thuis" if is_home else "Uit"
                mid = str(match.get("match_id", f"eshg_{rnd}_{idx}"))

                with st.container(border=True):
                    st.markdown(
                        f"**Ronde {rnd}** ({match.get('datum', '')}) · **{match['thuis']} – {match['uit']}** *({loc_tag})*"
                    )
                    choice = st.radio(
                        "Verwachting ESHG",
                        ["Winst ESHG", "Gelijk", "Verlies ESHG", "Open laten (meesimuleren)"],
                        index=0 if idx == 0 else 3,
                        horizontal=True,
                        key=f"scen_eshg_choice_{mid}",
                        label_visibility="collapsed",
                    )

                    if choice != "Open laten (meesimuleren)":
                        if use_exact:
                            default_eshg, default_opp = (
                                (3, 1) if choice == "Winst ESHG" else (2, 2) if choice == "Gelijk" else (1, 3)
                            )
                            sc1, sc2 = st.columns(2)
                            with sc1:
                                eshg_g = int(
                                    st.number_input(
                                        f"Goals {_ESHG_TEAM}",
                                        min_value=0,
                                        max_value=25,
                                        value=default_eshg,
                                        key=f"scen_eshg_g_{mid}",
                                    )
                                )
                            with sc2:
                                opp_g = int(
                                    st.number_input(
                                        f"Goals {opponent}",
                                        min_value=0,
                                        max_value=25,
                                        value=default_opp,
                                        key=f"scen_opp_g_{mid}",
                                    )
                                )
                            score_thuis = eshg_g if is_home else opp_g
                            score_uit = opp_g if is_home else eshg_g
                        else:
                            if choice == "Winst ESHG":
                                score_thuis, score_uit = (3, 1) if is_home else (1, 3)
                            elif choice == "Verlies ESHG":
                                score_thuis, score_uit = (1, 3) if is_home else (3, 1)
                            else:
                                score_thuis, score_uit = 2, 2

                        fixed_results.append(
                            {
                                **match,
                                "score_thuis": score_thuis,
                                "score_uit": score_uit,
                                "gespeeld": True,
                            }
                        )

        if st.button("Bereken Verwachte Stand", type="primary", width="stretch"):
            try:
                sim_df, sim_meta = simulate_scenario_horizon(
                    matches=matches,
                    max_round=int(target_round),
                    fixed_results=fixed_results,
                    simulate_unplayed=True,
                    n_simulations=1000,
                )
            except ValueError as error:
                st.error(f"De simulatie kon niet worden uitgevoerd: {error}")
            else:
                st.session_state["scenario_result"] = {
                    "type": "simulated",
                    "round": int(target_round),
                    "df": sim_df,
                    "meta": sim_meta,
                }

    # =========================================================================
    # MODUS B: HANDMATIG SCENARIO (MEERDERE RONDES)
    # =========================================================================
    else:
        use_exact = st.checkbox(
            "Exacte uitslagen invullen (voor doelsaldo)",
            value=False,
            key="scenario_exact_manual",
        )
        if not use_exact:
            st.caption(
                "Zonder exacte uitslag rekent Winst/Gelijk/Verlies met een standaard doelsaldo van +2 / 0 / -2."
            )

        rounds_in_horizon = sorted({_round_number(m) for m in horizon_matches if _round_number(m) is not None})
        for rnd in rounds_in_horizon:
            round_fixtures = [m for m in horizon_matches if _round_number(m) == rnd]
            with st.expander(f"Speelronde {rnd} ({round_fixtures[0].get('datum', '')})", expanded=(rnd == first_eshg_round)):
                for idx, match in enumerate(round_fixtures):
                    mid = str(match.get("match_id", f"man_{rnd}_{idx}"))
                    thuis = str(match["thuis"]).strip()
                    uit = str(match["uit"]).strip()
                    label_prefix = "🏑 " if _is_eshg_match(match) else ""

                    st.markdown(f"{label_prefix}**{thuis} – {uit}**")
                    opt_home = f"Winst {thuis}"
                    opt_draw = "Gelijk"
                    opt_away = f"Winst {uit}"
                    choice = st.radio(
                        f"Uitslag {thuis} - {uit}",
                        ["Overslaan", opt_home, opt_draw, opt_away],
                        index=0,
                        horizontal=True,
                        key=f"man_choice_{mid}",
                        label_visibility="collapsed",
                    )

                    if choice != "Overslaan":
                        if use_exact:
                            def_h, def_a = (
                                (3, 1) if choice == opt_home else (1, 3) if choice == opt_away else (2, 2)
                            )
                            c1, c2 = st.columns(2)
                            with c1:
                                h_goals = int(
                                    st.number_input(
                                        f"Goals {thuis}",
                                        min_value=0,
                                        max_value=25,
                                        value=def_h,
                                        key=f"man_hg_{mid}",
                                    )
                                )
                            with c2:
                                a_goals = int(
                                    st.number_input(
                                        f"Goals {uit}",
                                        min_value=0,
                                        max_value=25,
                                        value=def_a,
                                        key=f"man_ag_{mid}",
                                    )
                                )
                            score_thuis, score_uit = h_goals, a_goals
                        else:
                            outcome_key = (
                                "home" if choice == opt_home else "away" if choice == opt_away else "draw"
                            )
                            score_thuis, score_uit = _scores_from_outcome(outcome_key)

                        fixed_results.append(
                            {
                                **match,
                                "score_thuis": score_thuis,
                                "score_uit": score_uit,
                                "gespeeld": True,
                            }
                        )
                    if idx < len(round_fixtures) - 1:
                        st.divider()

        if st.button("Bereken Virtuele Stand", type="primary", width="stretch"):
            if not fixed_results:
                st.session_state.pop("scenario_result", None)
                st.warning("Selecteer minimaal één wedstrijd (Winst/Gelijk/Verlies) om te berekenen.")
            else:
                try:
                    man_df, man_meta = simulate_scenario_horizon(
                        matches=matches,
                        max_round=int(target_round),
                        fixed_results=fixed_results,
                        simulate_unplayed=False,
                    )
                except ValueError as error:
                    st.error(f"De virtuele stand kon niet worden berekend: {error}")
                else:
                    st.session_state["scenario_result"] = {
                        "type": "manual",
                        "round": int(target_round),
                        "df": man_df,
                        "meta": man_meta,
                        "matches": fixed_results,
                    }

    # =========================================================================
    # RESULTAAT WEERGAVE
    # =========================================================================
    result = st.session_state.get("scenario_result")
    if not isinstance(result, dict):
        return

    res_df = result.get("df")
    if not isinstance(res_df, pd.DataFrame) or res_df.empty:
        return

    if result.get("type") == "simulated":
        sim_meta = result.get("meta", {})
        eshg_info = sim_meta.get("eshg", {})
        res_round = result.get("round", target_round)

        st.subheader(f"Verwachte stand na speelronde {res_round}")
        st.caption(
            f"Gebaseerd op jouw ingevulde ESHG-uitslagen + 1.000 simulaties van de "
            f"{sim_meta.get('simulated_other_count', 0)} overige poulewedstrijden t/m ronde {res_round}."
        )

        if eshg_info:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric(
                "Verwachte positie ESHG",
                f"{eshg_info['verw_pos']:.1f}e",
                delta=f"Huidig: {eshg_info['huidig']}e" if eshg_info.get("huidig") else None,
                delta_color="off",
            )
            k2.metric("Bandbreedte (10%–90%)", f"{eshg_info['p10']}e – {eshg_info['p90']}e")
            k3.metric("Verwachte punten", f"{eshg_info['verw_pt']:.1f} pt")
            k4.metric("Kans Linkerrijtje", f"{eshg_info['left_pct']:.0f}%")

        st.dataframe(
            res_df.style.apply(_highlight_eshg, axis=1).format(
                {
                    "Verw. Pos": "{:.1f}",
                    "Verw. PT": "{:.1f}",
                    "Top 3 (%)": "{:.1f}%",
                    "Linkerrijtje (%)": "{:.1f}%",
                }
            ),
            hide_index=True,
            width="stretch",
            height=(len(res_df) + 1) * 36,
        )
    else:
        st.subheader("Virtuele ranglijst")
        display_standings = res_df.copy()
        display_standings["Verschil"] = display_standings["Pos_Verschil"].map(
            _difference_label
        )
        display_standings = display_standings[_MANUAL_DISPLAY_COLUMNS]
        st.dataframe(
            display_standings.style.apply(_highlight_eshg, axis=1),
            hide_index=True,
            width="stretch",
            height=(len(display_standings) + 1) * 36,
        )
        st.subheader("Conclusie")
        _render_manual_conclusion(
            res_df,
            result.get("matches", []),
        )