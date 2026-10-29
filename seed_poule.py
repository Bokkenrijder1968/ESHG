import pandas as pd
import json
from pathlib import Path

csv_path = Path("Uitslagen.csv")
output_path = Path("data/poule_matches.json")
output_path.parent.mkdir(parents=True, exist_ok=True)

if csv_path.exists():
    df = pd.read_csv(csv_path)
    poule_matches = []
    
    for idx, row in df.iterrows():
        status = row["Speelronde/Status"]
        uitslag = str(row["Uitslag/Tijd"])
        datum = str(row["Datum"])
        thuis = str(row["Thuis"]).strip()
        uit = str(row["Uit"]).strip()
        
        gespeeld = (status == "Gespeeld" and " - " in uitslag)
        score_thuis, score_uit = None, None
        if gespeeld:
            parts = uitslag.split(" - ")
            score_thuis, score_uit = int(parts[0].strip()), int(parts[1].strip())
            
        poule_matches.append({
            "match_id": f"poule_{idx}_{datum}_{thuis}_{uit}".replace(" ", "_"),
            "datum": datum,
            "thuis": thuis,
            "uit": uit,
            "score_thuis": score_thuis,
            "score_uit": score_uit,
            "gespeeld": gespeeld
        })
        
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(poule_matches, f, ensure_ascii=False, indent=2)
    print(f"Succesvol {len(poule_matches)} wedstrijden geëxporteerd naar {output_path}!")
else:
    print("CSV-bestand niet gevonden in de hoofdmap.")