"""Lance l'app « Départs ».  python run.py [--demo] [--no-browser] [--port 8765]"""

import argparse
import os

parser = argparse.ArgumentParser(description="Agent Vols — app locale")
parser.add_argument("--demo", action="store_true", help="rejoue une recherche enregistrée (sans clé, sans quota)")
parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
parser.add_argument("--port", type=int, default=8765)
args = parser.parse_args()

if args.demo:
    os.environ["AGENT_VOLS_DEMO"] = "1"
if args.no_browser:
    os.environ["AGENT_VOLS_NO_BROWSER"] = "1"
os.environ["AGENT_VOLS_PORT"] = str(args.port)

from webapp.app import main  # noqa: E402  (les variables d'env doivent être posées avant l'import)

main()
