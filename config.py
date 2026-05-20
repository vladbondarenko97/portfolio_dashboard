import os
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT.parent / "CME_Data"
DB_PATH = DATA_DIR / "portfolio.db"
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

# Ensure Data Directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Centralized API Keys & Config
DATABENTO_API_KEY = required_env("DATABENTO_API_KEY", alt_name="DB_API_KEY")
FRED_API_KEY = optional_env("FRED_API_KEY", default="")
ALPHA_VANTAGE_KEY = optional_env("ALPHA_VANTAGE_KEY", default="")
GOLD_API_KEY = optional_env("GOLD_API_KEY", default="")
EBAY_APP_ID = optional_env("EBAY_APP_ID", default="")
EBAY_CERT_ID = optional_env("EBAY_CERT_ID", default="")
EMAIL_SENDER = optional_env("EMAIL_SENDER", default="")
EMAIL_PASSWORD = optional_env("EMAIL_PASSWORD", default="")
CME_LOGIN_USERNAME = optional_env("CME_LOGIN_USERNAME", default="")
CME_LOGIN_PASSWORD = optional_env("CME_LOGIN_PASSWORD", default="")
