import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN: str = os.getenv("TELEGRAM_TOKEN", "")
MAX_RESULTS: int = int(os.getenv("MAX_RESULTS", "30"))
HEADLESS: bool = os.getenv("HEADLESS", "true").lower() == "true"
