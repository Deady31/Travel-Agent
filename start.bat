@echo off
rem Double-clic pour lancer l'app "Départs". Ajoute --demo pour tester sans clé.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Premiere installation...
  python -m venv .venv || goto :error
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt || goto :error
)
if not exist ".env" (
  echo Pas de fichier .env : lancement en mode demo. Copie .env.example en .env pour les vraies recherches.
  ".venv\Scripts\python.exe" run.py --demo %*
) else (
  ".venv\Scripts\python.exe" run.py %*
)
goto :eof
:error
echo Installation impossible. Verifie que Python 3.11+ est installe.
pause
