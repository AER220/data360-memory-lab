"""Settings lookup: environment variables, then a local .env file, then Streamlit secrets.

Works the same on a laptop (.env or nothing at all) and on Streamlit Community Cloud
(App settings > Secrets). Missing secrets never raise. Key values are never printed or logged.
"""
# Here I read settings and API keys from the environment, .env or Streamlit secrets.
from __future__ import annotations

import os

from .paths import ROOT

# I remember whether .env was read, so it is parsed only once per process.
_dotenv_loaded = False


# A switch the tests use to ignore local settings.
def _skip_local() -> bool:
    # Tests set this so a developer's own .env or secrets.toml can never trigger real API calls.
    return os.environ.get("DATA360_SKIP_LOCAL_CONFIG", "") == "1"


# I read .env myself instead of adding the python-dotenv package, to keep requirements small.
def load_dotenv() -> None:
    """Read KEY=VALUE lines from .env (if present) without extra dependencies. Existing env vars win."""
    global _dotenv_loaded
    if _dotenv_loaded or _skip_local():
        return
    _dotenv_loaded = True
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            # I drop inline comments and surrounding quotes, so KEY="value"  # note still works.
            v = v.split(" #", 1)[0].strip().strip('"').strip("'")
            if v:
                # setdefault means a real environment variable always beats the .env file.
                os.environ.setdefault(k.strip(), v)


# Streamlit Cloud keeps keys in Secrets. Locally there is usually no secrets.toml, and plain
# st.secrets access would raise an error, so I probe first.
def _from_secrets(name: str) -> str:
    if _skip_local():
        return ""
    try:
        import streamlit as st

        # load_if_toml_exists returns False instead of raising when no secrets file exists.
        if not st.secrets.load_if_toml_exists():  # no secrets.toml: fine, just nothing there
            return ""
        value = st.secrets.get(name)
    # Any problem with secrets (missing, malformed) just means 'no value', never a crash.
    except Exception:  # never let a missing or malformed secrets file crash the app
        return ""
    # I only accept top-level text values; a [section] table is not a key.
    if value is None or isinstance(value, dict) or hasattr(value, "keys"):
        return ""
    return str(value).strip()


# Single lookup used by the whole app: environment (including .env) first, then Streamlit secrets,
# then the default.
def setting(name: str, default: str = "") -> str:
    """Environment variable (including .env), else a top-level Streamlit secret, else default."""
    load_dotenv()
    value = os.environ.get(name, "").strip()
    if value:
        return value
    return _from_secrets(name) or default


# True when a setting has a non-empty value, used to decide which providers to offer.
def has(name: str) -> bool:
    return bool(setting(name))
