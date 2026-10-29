@echo off
title ESHG Dashboard
echo ========================================================
echo   ESHG Dashboard opstarten...
echo ========================================================

:: 1. Navigeer direct naar de projectmap
cd /d "C:\Users\20193614\Documents\ESHG"

:: 2. Activeer de Anaconda base environment via het volledige pad
call "C:\Users\20193614\AppData\Local\anaconda3\Scripts\activate.bat" base

:: 3. Start het Streamlit dashboard (Streamlit opent zelf automatisch je browser)
echo.
echo [2/2] Streamlit Dashboard starten...
python -m streamlit run app.py

:: Pause zorgt dat het venster openblijft als er onverhoopt een fout optreedt
pause