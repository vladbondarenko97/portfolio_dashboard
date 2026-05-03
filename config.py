import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DOTENV_PATH = PROJECT_ROOT / ".env"

try:
    from dotenv import load_dotenv
    load_dotenv(DOTENV_PATH)
except ImportError:
    pass


def required_env(name, alt_name=None):
    value = os.environ.get(name)
    if (value is None or value == "") and alt_name:
        value = os.environ.get(alt_name)
    if value is None or value == "":
        if alt_name:
            raise EnvironmentError(
                f"Missing required environment variable '{name}' (or fallback '{alt_name}')"
            )
        raise EnvironmentError(f"Missing required environment variable '{name}'")
    return value


def optional_env(name, default=None, alt_name=None):
    value = os.environ.get(name)
    if value is None and alt_name:
        value = os.environ.get(alt_name)
    return value if value is not None else default
