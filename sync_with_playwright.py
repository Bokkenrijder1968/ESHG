import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from playwright.sync_api import sync_playwright

# ==========================================================
# CONFIGURATIE
# ==========================================================
MATCHES_FILE = "data/all_matches.json"

# Plak hier de publieke URL van jouw team op hockey.nl (waar de stand/uitslagen staan)
TARGET_URL = "https://www.hockey.nl/match-center#/team/3081|182843/results" 

# ==========================================================
# HULPFUNCTIES VOOR NORMALISATIE & PARSING
# ==========================================================
def normalize_team(name: str) -> str:
    if not name:
        return ""
    clean = name.strip().lower()
    clean = re.sub(r"[\s\-_]+", "", clean)
    if "eshg" in clean or "donquishoot" in clean:
        return "donquishooth3"
    return clean

def is_eshg(team_name: str) -> bool:
    return normalize_team(team_name) == "donquishooth3"

def clean_address(raw_addr: Optional[str]) -> Optional[str]:
    if not raw_addr:
        return None
    lines = [line.strip() for line in raw_addr.split("\n") if line.strip()]
    return ", ".join(lines)

def extract_matches(payload: dict) -> List[dict]:
    data_block = payload.get("data", payload)
    poules = data_block.get("poules", []) if isinstance(data_block, dict) else []
    all_matches = []
    for poule in poules:
        all_matches.extend(poule.get("matches", []))
    return all_matches if all_matches else data_block.get("matches", [])

# ==========================================================
# SYNCHRONISATIE LOGICA
# ==========================================================
def update_matches_file(api_payload: dict, filepath: str = MATCHES_FILE):
    p = Path(filepath)
    if not p.exists():
        print(f"❌ Bestand '{filepath}' niet gevonden.")
        return

    with open(p, "r", encoding="utf-8") as f:
        local_matches: List[Dict[str, Any]] = json.load(f)

    api_matches = extract_matches(api_payload)
    print(f"🔍 {len(api_matches)} wedstrijden verwerkt uit de opgevangen API-call.")

    api_lookup: Dict[Tuple[str, str], dict] = {}
    for m in api_matches:
        home_name = m.get("home", {}).get("name")
        away_name = m.get("away", {}).get("name")
        if home_name and away_name:
            api_lookup[(normalize_team(home_name), normalize_team(away_name))] = m

    matched_count = 0
    scores_updated = 0
    eshg_enriched = 0

    for match in local_matches:
        match.pop("status", None)
        match.pop("datum_tijd", None)

        thuis = match.get("thuis", "")
        uit = match.get("uit", "")
        key = (normalize_team(thuis), normalize_team(uit))

        if key not in api_lookup:
            continue

        matched_count += 1
        remote = api_lookup[key]
        status = (remote.get("status") or "").lower()

        match["knhb_match_id"] = remote.get("id")

        remote_date = remote.get("date")
        if remote_date:
            match["datum"] = remote_date.split("T")[0]
            if "T" in remote_date:
                tijd_str = remote_date.split("T")[1][:5]
                match["tijd"] = tijd_str if tijd_str != "00:00" else None
            else:
                match["tijd"] = None

        is_gespeeld = (status == "final")
        match["gespeeld"] = is_gespeeld

        if remote.get("round") is not None:
            match["ronde"] = remote["round"]

        if is_gespeeld:
            score = remote.get("score") or {}
            home_s = score.get("home")
            away_s = score.get("away")

            if home_s is not None and away_s is not None:
                match["score_thuis"] = home_s
                match["score_uit"] = away_s
                scores_updated += 1

                if is_eshg(thuis):
                    match["resultaat"] = "W" if home_s > away_s else ("G" if home_s == away_s else "V")
                    match["punten"] = 3 if home_s > away_s else (1 if home_s == away_s else 0)
                elif is_eshg(uit):
                    match["resultaat"] = "W" if away_s > home_s else ("G" if away_s == home_s else "V")
                    match["punten"] = 3 if away_s > home_s else (1 if away_s == home_s else 0)

        location = remote.get("location") or {}
        field = location.get("field") or {}
        field_type = field.get("type")
        if field_type:
            match["veld_type"] = field_type

        if is_eshg(thuis) or is_eshg(uit):
            facility = location.get("facility") or {}
            fac_name = facility.get("name")
            fac_addr = clean_address(facility.get("address"))
            f_name = field.get("name")

            if fac_name:
                match["locatie_accommodatie"] = fac_name
            if fac_addr:
                match["locatie_adres"] = fac_addr
            if f_name:
                match["veld_naam"] = f_name

            eshg_enriched += 1

    with open(p, "w", encoding="utf-8") as f:
        json.dump(local_matches, f, indent=2, ensure_ascii=False)

    print("\n" + "="*45)
    print("📋 AUTOMATISCHE PLAYWRIGHT UPDATE VOLTOOID")
    print("="*45)
    print(f"✅ Gematchte wedstrijden:          {matched_count} / {len(local_matches)}")
    print(f"⚽ Scores & standen bijgewerkt:    {scores_updated}")
    print(f"📍 Don Quishoot info verrijkt:      {eshg_enriched}")
    print(f"💾 Opgeslagen in:                  {filepath}")
    print("="*45)

# ==========================================
# PLAYWRIGHT RUNNER
# ==========================================
def run():
    captured_data = {}

    with sync_playwright() as p:
        # headless=True voor achtergrondgebruik (zet op False om mee te kijken)
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        def handle_response(response):
            # Onderschep het poule- of team-request naar hockeyweerelt
            if "app.hockeyweerelt.nl/poules/" in response.url and response.status == 200:
                try:
                    data = response.json()
                    # Controleer of de response wedstrijden bevat
                    if "matches" in str(data):
                        captured_data["payload"] = data
                        print(f"🎯 Doelwit response onderschept van: {response.url[:60]}...")
                except Exception:
                    pass

        page.on("response", handle_response)

        print(f"🌐 Headless browser navigeert naar: {TARGET_URL}")
        try:
            page.goto(TARGET_URL, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"Navigatiefout of timeout: {e}")

        # Wacht maximaal een paar seconden tot het verzoek is geland
        page.wait_for_timeout(3000)
        browser.close()

    if "payload" in captured_data:
        update_matches_file(captured_data["payload"])
    else:
        print("❌ Geen wedstrijden-API kunnen onderscheppen. Controleer TARGET_URL.")

if __name__ == "__main__":
    run()