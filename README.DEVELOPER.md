# Developer guide

Technische documentatie voor mensen die het dashboard willen onderhouden of
uitbreiden.

## Projectstructuur

```text
ESHG/
├── app.py
├── data/
│   └── all_matches.json
├── src/
│   ├── calculations.py
│   ├── constants.py
│   └── views/
│       ├── input_view.py
│       ├── matchup_view.py
│       ├── players_view.py
│       ├── scenario_view.py
│       ├── simulation_view.py
│       ├── table_view.py
│       └── trends_view.py
├── sync_with_playwright.py
├── .github/workflows/sync.scores.yml
├── requirements.txt
└── Start_ESHG.bat
```

Er is momenteel geen `oud/`, `.devcontainer/` of `.vscode/`-configuratie meer
in de repository. Er is ook geen apart importscript meer; de actieve dataset
wordt onderhouden via de applicatie en de synchronisatie.

## Lokale ontwikkeling

Maak bij voorkeur een lokale virtuele omgeving aan:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

De runtime-dependencies zijn:

- `streamlit` voor de gebruikersinterface;
- `pandas` voor tabellen en dataverwerking;
- `numpy` voor numerieke berekeningen;
- `plotly` voor interactieve grafieken;
- `matplotlib` voor aanvullende visualisaties.

De synchronisatie gebruikt daarnaast Playwright. Die dependency staat niet in
`requirements.txt`, omdat Playwright niet nodig is om het dashboard lokaal te
draaien. De GitHub Actions-workflow installeert Playwright en Chromium zelf.

## Applicatieflow

[`app.py`](app.py) configureert Streamlit en maakt zeven tabs aan. Elke tab
delegeert de weergave aan een functie in `src/views/`.

De belangrijkste gegevensstroom is:

```text
data/all_matches.json
        ↓
src/calculations.py
        ↓
src/views/*
        ↓
Streamlit-interface
```

De invoerview leest en schrijft wedstrijdgegevens rechtstreeks. De overige
views gebruiken berekeningen uit `src/calculations.py` en presenteren de
resultaten als tabellen, statistieken of grafieken.

## Databron en datamodel

[`data/all_matches.json`](data/all_matches.json) is de enige actieve bron van
waarheid. Het bestand bevat zowel algemene competitiegegevens als extra
informatie die handmatig per Don Quishoot-wedstrijd kan worden toegevoegd.

Veelgebruikte velden zijn:

- `match_id`, `ronde`, `datum`, `tijd`;
- `thuis`, `uit`, `tegenstander`;
- `score_thuis`, `score_uit`, `gespeeld`;
- `resultaat`, `punten`;
- `goals`, `kwarten`, `kwarten_bijgehouden`;
- `corners`, `corners_bijgehouden`;
- `extra_stats`, `notities`;
- locatievelden zoals `locatie_adres`, `veld_naam` en `veld_type`.

Bij wijzigingen aan het datamodel moeten minstens deze onderdelen worden
gecontroleerd:

1. de laad- en opslaglogica in `src/views/input_view.py`;
2. de berekeningen in `src/calculations.py`;
3. alle views die het gewijzigde veld gebruiken;
4. de synchronisatielogica in `sync_with_playwright.py`;
5. bestaande records in `data/all_matches.json`.

Gebruik geen historische kopieën als tweede actieve databron. Dat voorkomt
onduidelijkheid over welke uitslag leidend is.

## Synchronisatie

[`sync_with_playwright.py`](sync_with_playwright.py) opent de publieke
hockey.nl-pagina met Playwright en onderschept een relevante API-response.
Daarna:

1. worden de wedstrijden uit de API-response gehaald;
2. worden teams genormaliseerd voor matching;
3. worden lokale wedstrijden gekoppeld aan API-wedstrijden;
4. worden status, datum, tijd, score, ronde en locatie bijgewerkt;
5. wordt `data/all_matches.json` opnieuw opgeslagen.

De GitHub Actions-workflow
[`sync.scores.yml`](.github/workflows/sync.scores.yml) draait op schema en kan
ook handmatig worden gestart. Als de data verandert, commit de workflow het
bijgewerkte JSON-bestand naar `main`.

Let bij wijzigingen op:

- de externe website/API kan veranderen;
- de onderschepte response is niet volledig onder controle van dit project;
- Playwright en Chromium moeten in de workflow beschikbaar zijn;
- een synchronisatie mag handmatig ingevoerde extra wedstrijdinformatie niet
  onbedoeld overschrijven.

## Nieuwe functionaliteit toevoegen

Voor een nieuwe dashboardsectie:

1. plaats de berekeningslogica in `src/calculations.py` als die herbruikbaar is;
2. plaats de presentatie in een aparte view onder `src/views/`;
3. importeer de renderfunctie in `app.py`;
4. voeg een tab toe op een consistente plek;
5. gebruik bestaande foutafhandeling en Nederlandse labels;
6. controleer dat lege of onvolledige wedstrijddata geen crash veroorzaakt.

Houd data-validatie en presentatie zoveel mogelijk gescheiden. Berekeningen
horen niet afhankelijk te zijn van Streamlit als ze ook door andere views
kunnen worden gebruikt.

## Wijzigingen controleren

Voer minimaal syntaxcontrole uit:

```powershell
python -m compileall -q app.py src sync_with_playwright.py
```

Start daarna lokaal:

```powershell
python -m streamlit run app.py
```

Controleer minstens:

- openen van alle zeven tabs;
- inladen van `data/all_matches.json`;
- wedstrijdinvoer en opslaan;
- lege datasets en ontbrekende scores;
- scenario- en simulatie-uitkomsten;
- het gedrag van de synchronisatie niet uitvoeren tegen productie zonder
  expliciete aanleiding.

## Onderhoudsafspraken

- Wijzig alleen direct relevante bestanden.
- Bewaar geen gegenereerde `__pycache__`- of `.pyc`-bestanden.
- Houd `data/all_matches.json` als enige actieve wedstrijddataset aan.
- Voeg nieuwe Python-dependencies bewust toe aan een dependencybestand.
- Werk documentatie bij als startcommando's, workflows of datavelden wijzigen.
- Controleer vóór een wijziging aan de workflow of GitHub Actions naar de juiste
  branch en het juiste datadpad schrijft.
