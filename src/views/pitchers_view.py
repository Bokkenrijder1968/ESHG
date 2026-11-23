from datetime import date

import pandas as pd
import streamlit as st  # type: ignore[import-not-found]

from src.calculations import (
    add_pitcher_record,
    delete_pitcher_record,
    get_pitchers,
    set_pitcher_collected,
)
from src.constants import ENABLE_PITCHERS, SQUAD_PLAYERS


def render_pitchers_view() -> None:
    st.title("🍺 Pitchers")

    if not ENABLE_PITCHERS:
        st.info("De pitcher-registratie staat momenteel uitgeschakeld (`ENABLE_PITCHERS = False` in `src/constants.py`).")
        return

    try:
        records = get_pitchers()
    except ValueError as error:
        st.error(f"Pitchers konden niet worden geladen: {error}")
        return

    open_records = [r for r in records if not r.get("gehaald")]
    collected_records = [r for r in records if r.get("gehaald")]

    open_total = sum(int(r.get("aantal", 1)) for r in open_records)
    collected_total = sum(int(r.get("aantal", 1)) for r in collected_records)
    unique_debtors = len({str(r.get("speler", "")) for r in open_records if r.get("speler")})

    k1, k2, k3 = st.columns(3)
    k1.metric("Nog te innen pitchers", open_total)
    k2.metric("Spelers met openstaand", unique_debtors)
    k3.metric("Reeds gehaald", collected_total)

    st.subheader("Openstaand per speler")
    if not open_records:
        st.success("Er staan momenteel geen pitchers meer open.")
    else:
        summary_counts: dict[str, int] = {}
        for item in open_records:
            speler = str(item.get("speler", "Onbekend"))
            summary_counts[speler] = summary_counts.get(speler, 0) + int(item.get("aantal", 1))

        summary_df = pd.DataFrame(
            [
                {"Speler": speler, "Openstaande pitchers": count}
                for speler, count in sorted(
                    summary_counts.items(),
                    key=lambda x: (-x[1], x[0].casefold()),
                )
            ]
        )
        st.dataframe(summary_df, hide_index=True, width="stretch")

        st.subheader("Te innen lijst (details)")
        open_sorted = sorted(
            open_records,
            key=lambda r: str(r.get("datum", "")),
            reverse=True,
        )
        open_df = pd.DataFrame(
            [
                {
                    "Datum": r.get("datum", ""),
                    "Speler": r.get("speler", ""),
                    "Aantal": int(r.get("aantal", 1)),
                    "Reden": r.get("reden", ""),
                }
                for r in open_sorted
            ]
        )
        st.dataframe(open_df, hide_index=True, width="stretch")

        action_labels = {
            f"{r.get('datum', '')} — {r.get('speler', '')} ({r.get('aantal', 1)}x: {r.get('reden', '')})": str(r.get("id"))
            for r in open_sorted
        }
        selected_action_label = st.selectbox(
            "Selecteer regel om af te vinken of te verwijderen",
            options=list(action_labels.keys()),
            key="pitcher_open_action_select",
        )
        selected_id = action_labels[selected_action_label]

        b1, b2 = st.columns([2, 1])
        with b1:
            if st.button("✅ Markeer als gehaald", type="primary", width="stretch"):
                set_pitcher_collected(selected_id, True)
                st.rerun()
        with b2:
            if st.button("🗑️ Verwijder regel", width="stretch"):
                delete_pitcher_record(selected_id)
                st.rerun()

    st.subheader("Nieuwe pitcher toevoegen")
    with st.form("new_pitcher_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            speler = st.selectbox("Speler", options=SQUAD_PLAYERS)
        with c2:
            datum = st.date_input("Datum", value=date.today())
        with c3:
            aantal = st.number_input("Aantal", min_value=1, max_value=10, value=1)

        reden = st.text_input(
            "Reden",
            placeholder="Bijv. Te laat, groene/gele kaart, training...",
        )
        submitted = st.form_submit_button("Pitcher toevoegen", type="primary", width="stretch")
        if submitted:
            add_pitcher_record(speler, datum.isoformat(), int(aantal), reden)
            st.success(f"Pitcher voor {speler} toegevoegd.")
            st.rerun()

    with st.expander("Historie · Reeds gehaalde pitchers", expanded=False):
        if not collected_records:
            st.caption("Nog geen afgehandelde pitchers.")
        else:
            collected_sorted = sorted(
                collected_records,
                key=lambda r: str(r.get("datum", "")),
                reverse=True,
            )
            hist_df = pd.DataFrame(
                [
                    {
                        "Datum": r.get("datum", ""),
                        "Speler": r.get("speler", ""),
                        "Aantal": int(r.get("aantal", 1)),
                        "Reden": r.get("reden", ""),
                        "Gehaald op": r.get("gehaald_op") or "—",
                    }
                    for r in collected_sorted
                ]
            )
            st.dataframe(hist_df, hide_index=True, width="stretch")