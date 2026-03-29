import os
from pathlib import Path
from dotenv import load_dotenv

# Base Directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# Trading 212 API
T212_API_KEY = os.getenv("T212_API_KEY")
T212_API_SECRET = os.getenv("T212_API_SECRET")
T212_DEMO = os.getenv("T212_DEMO", "true").lower() == "true"

# Market Data
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

# Telegram Notification
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Risk Management
MAX_ALLOCATION_PERCENTAGE = float(os.getenv("MAX_ALLOCATION_PERCENTAGE", "10.0"))

# Operational
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"
ACCOUNT_BASE_CURRENCY = os.getenv("ACCOUNT_BASE_CURRENCY", "EUR")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPERATING_TIMEZONE = os.getenv("OPERATING_TIMEZONE", "WET")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# SQLite Database
DATABASE_URL = f"sqlite:///{BASE_DIR}/trading-bot.sqlite"

# NYSE Operating Hours (WET)
NYSE_OPEN = "14:30"
NYSE_CLOSE = "21:00"
