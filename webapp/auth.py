"""Accès par mot de passe (APP_PASSWORD) avec cookie de session signé.

- Sans APP_PASSWORD en local : pas de mot de passe (usage sur ton PC).
- Sur Vercel : APP_PASSWORD obligatoire (12 caractères min.), sinon tout est bloqué.
- La clé qui signe les cookies n'est jamais le mot de passe brut : SESSION_SECRET si défini,
  sinon une clé dérivée par PBKDF2 (un cookie volé ne permet pas de tester des mots de passe à la chaîne).
- Changer SESSION_SECRET déconnecte tous les appareils sans changer le mot de passe.
"""

import hashlib
import hmac
import os
import time
from functools import lru_cache

COOKIE = "av_session"
SESSION_DAYS = 30
MIN_PASSWORD_LENGTH = 12
PBKDF2_ITERATIONS = 200_000
PUBLIC_PATHS = {
    "/login", "/api/login", "/manifest.webmanifest", "/sw.js",
    "/static/login.html", "/static/login.js", "/static/styles.css", "/static/js/api.js",
    "/static/icons/icon.svg", "/static/icons/icon-192.png", "/static/icons/icon-512.png",
    "/static/icons/apple-touch-icon.png",
}


def password() -> str:
    return os.getenv("APP_PASSWORD", "")


def on_vercel() -> bool:
    return bool(os.getenv("VERCEL"))


def config_error() -> str | None:
    """Raison de refuser de servir l'app en ligne, ou None si la configuration est sûre."""
    if not on_vercel():
        return None
    if not password():
        return "APP_PASSWORD manquant : ajoute-le dans les variables d'environnement Vercel."
    if len(password()) < MIN_PASSWORD_LENGTH:
        return f"APP_PASSWORD trop court : {MIN_PASSWORD_LENGTH} caractères minimum (une phrase de passe)."
    return None


@lru_cache(maxsize=4)
def _derive_key(secret: str, session_secret: str) -> bytes:
    if session_secret:
        return hashlib.sha256(f"agent-vols:{session_secret}".encode()).digest()
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), b"agent-vols-session-v1", PBKDF2_ITERATIONS)


def _key(secret: str) -> bytes:
    return _derive_key(secret, os.getenv("SESSION_SECRET", ""))


def _sign(expires: int, secret: str) -> str:
    return hmac.new(_key(secret), f"agent-vols:{expires}".encode(), hashlib.sha256).hexdigest()


def make_token(secret: str, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + SESSION_DAYS * 86400)
    return f"{expires}.{_sign(expires, secret)}"


def valid_token(token: str | None, secret: str, now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    expires_raw, signature = token.split(".", 1)
    if not expires_raw.isdigit() or int(expires_raw) < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(signature, _sign(int(expires_raw), secret))


def check_password(candidate: str) -> bool:
    expected = password()
    return bool(expected) and hmac.compare_digest(candidate.encode(), expected.encode())


def is_public(path: str) -> bool:
    return path in PUBLIC_PATHS
