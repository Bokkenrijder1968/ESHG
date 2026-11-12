# ESHG H1 Dashboard 🏑

Hét digitale brein achter ESHG H1. Niet omdat we alles zo goed onder controle hebben, was het maar zo'n feest, maar omdat het leuk is na een wedstrijd nét iets meer onzin bij te houden dan strikt noodzakelijk.

Dit dashboard helpt bij het bijhouden, bekijken en voorspellen van het seizoen. Van wedstrijdinvoer tot ELO-rating: alles staat bij elkaar op één plek.

## Wat kun je ermee?

### 📝 Wedstrijden invoeren

Eigen uitslagen en wedstrijdinformatie vastzetten. Denk aan:

- score en resultaat;
- doelpuntenmakers en assists;
- doelpunttype, zoals veldgoal, strafcorner of strafbal;
- kwartstanden;
- strafcorners;
- notities, afwezigen en andere extra wedstrijdinformatie.

### 🏆 Stand & schema

Bekijk de actuele competitie-stand, uitslagen en het resterende programma.
Dit wordt uiteraard automatisch bijgewerkt op basis van informatie van hockeynl match center.
De stand laat ook zien hoeveel plaatsen een team is gestegen of gedaald ten opzichte van de vorige gespeelde ronde.

### 🎯 Matchup & analyse

Vergelijk ESHG met de volgende tegenstander(s) op basis van:

- onderlinge resultaten;
- recente vorm;
- gedeelde tegenstanders;
- verwachte scores (en winkans);
- wedstrijdlocatie, reistijd en verzameltijd;
- een Google Maps-link naar de accommodatie.

### 🔮 Scenario calculator

Speel wat-als met het resterende programma (voor nu komende ronde).
Wat gebeurt er met de stand als iedereen wint, verliest of als specifieke uitslagen worden ingevuld?

### 📊 Spelers & stats

Bekijk topscorers, assistkoningen, MVP-statistieken en gouden duo's.
Hier zit ook een controle naar de wedstrijden waarin een speler scoorde of een assist gaf.

### 📈 Trends & fysiek

Ontdek in welk kwart we vlammen, wanneer het even minder loopt en hoe de verdeling tussen veldgoals en corners eruitziet (nog voor weinig wedstrijden bijgehouden, zegt later meer).

### 🎲 Simulaties & ELO

Gebruik Monte Carlo-simulaties en ELO-ratings om de kansen en krachtsverhoudingen in de competitie te verkennen.
Geen garantie op promotie, wel voer voor groepsapps, zeer tactische discussies en gezonde zelfoverschatting.

## Starten (als je het niet via de link wilt doen)

### Windows

Als Python en de dependencies al beschikbaar zijn:

```powershell
python -m streamlit run app.py
```

Of gebruik [`Start_ESHG.bat`](Start_ESHG.bat) als je de lokale snelkoppeling gebruikt.

### Eenmalige installatie

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Daarna opent Streamlit het dashboard meestal op `http://localhost:8501`.

## Automatische updates

De competitiegegevens worden automatisch bijgewerkt via GitHub Actions.
Daarvoor wordt [`sync_with_playwright.py`](sync_with_playwright.py) volgens een schema uitgevoerd.
Het script haalt uitslagen en wedstrijdlocaties op en werkt [`data/all_matches.json`](data/all_matches.json) bij.

De synchronisatie is vooral bedoeld als gemak.
Controleer belangrijke wedstrijdgegevens altijd zelf voordat je er grote conclusies aan verbindt.

## Waar staat alles?

```text
app.py                         # Startpunt van het Streamlit-dashboard
src/                           # Berekeningen en schermen
data/all_matches.json          # Actieve wedstrijddata
sync_with_playwright.py        # Automatische gegevenssynchronisatie
Start_ESHG.bat                 # Lokale Windows-startknop
requirements.txt               # Python-dependencies
.github/workflows/             # Automatische GitHub Actions
```

Veel plezier ermee. En onthoud: een goede ELO-rating is mooi, maar drie punten bij de MOTM zijn beter