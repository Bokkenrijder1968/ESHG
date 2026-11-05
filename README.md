# ESHG Dashboard

Streamlit-dashboard voor wedstrijdinvoer, standen, matchups, spelersstatistieken,
trends en simulaties van Don Quishoot H3.

## Installatie

Gebruik Python 3.11 of nieuwer binnen de bestaande ondersteuning:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start het dashboard met:

```powershell
python -m streamlit run app.py
```

`Start_ESHG.bat` is een lokale Windows-snelkoppeling, maar bevat nog
gebruikersspecifieke paden en is daarom niet portable.

## Data

[`data/all_matches.json`](data/all_matches.json) is de huidige bron van waarheid
voor de applicatie. De views laden en bewaren wedstrijdgegevens rechtstreeks
via de functies in `src/calculations.py` en `src/views/input_view.py`.

De map `oud/` bevat historische exports en oudere datastructuren. Deze bestanden
worden niet door de dashboardcode geladen. Controleer vóór verwijdering of een
bestand als archief nodig is.

## Scripts en automatisering

- [`sync_with_playwright.py`](sync_with_playwright.py) haalt periodiek actuele
  uitslagen en locatiegegevens op. De GitHub Actions-workflow installeert
  hiervoor aanvullend Playwright en Chromium.
- [`seed_poule.py`](seed_poule.py) is een eenmalig/importscript voor een
  `Uitslagen.csv`-bestand. Het huidige script verwacht dat bestand in de
  hoofdmap; de bewaarde CSV staat momenteel onder `oud/`.

Deze losse scripts kunnen later zonder gedragswijziging naar een `scripts/`
map worden verplaatst. Dat moet dan gelijktijdig worden aangepast in
`.github/workflows/sync.scores.yml` en in de relatieve bestandspaden van de
scripts.

## Dependencies structureren

De dashboarddependencies staan in [`requirements.txt`](requirements.txt).
Playwright en `requests` worden nu alleen door de synchronisatieworkflow
geïnstalleerd, omdat ze niet nodig zijn om het dashboard lokaal te draaien.
Een volgende gecontroleerde stap is het scheiden van runtime- en
automatiseringsdependencies, bijvoorbeeld `requirements-dev.txt` of een
afzonderlijk `requirements-sync.txt`. Pas daarna moet de workflow naar dat
bestand verwijzen; voorkom dubbele of tegenstrijdige dependency-lijsten.

## Devcontainer

De configuratie in [`.devcontainer/devcontainer.json`](.devcontainer/devcontainer.json)
gebruikt Python 3.11 en start Streamlit automatisch na attach. De configuratie
verwijst nog naar een ontbrekende `README.md` (dit bestand lost dat op) en
optioneel naar `packages.txt`. Ook installeert zij `streamlit` los naast
`requirements.txt`. Dat kan later worden vereenvoudigd door alle Python-pakketten
uitsluitend via `requirements.txt` te installeren en alleen bestaande optionele
bestanden conditioneel te gebruiken.

## Data-opslag centraliseren

De applicatie gebruikt momenteel al één actieve dataset:
`data/all_matches.json`. De historische bestanden onder `oud/` en de
import-/synchronisatiescripts gebruiken echter verschillende formaten en
relatieve paden. Een veilige vervolgstap is een kleine data-laag met één
absolute projectroot, één schema en expliciete import/exportfuncties. Migreer
oude bestanden eerst naar een aparte archief- of importmap en verwijder niets
voordat de inhoud en herkomst zijn gecontroleerd.
