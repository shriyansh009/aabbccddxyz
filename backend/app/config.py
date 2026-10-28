"""Central configuration. Everything is overridable through environment variables."""
import os
from datetime import date

ELEXON_BASE_URL = os.getenv("ELEXON_BASE_URL", "https://data.elexon.co.uk/bmrs/api/v1")
DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
CACHE_FILE = os.path.join(DATA_DIR, "elexon_cache.json")
STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "static"))

# Purchase decisions are made in January 2026 for delivery on the following day,
# so delivery days run 2 Jan - 1 Feb 2026.
DECISION_MONTH_START = date(2026, 1, 1)
DECISION_MONTH_END = date(2026, 1, 31)
DELIVERY_START = date(2026, 1, 2)
DELIVERY_END = date(2026, 2, 1)

# Day-ahead auction gate closure is around 09:20 UK time on D-1 (EPEX). The user can
# change the cut-off in the UI; this is the default (hour, Europe/London local time).
DEFAULT_CUTOFF_HOUR = 9
TIMEZONE = "Europe/London"

# Forecast horizons (hours before delivery) analysed in the accuracy view.
HORIZONS_HOURS = [1, 2, 4, 6, 8, 12, 16, 20, 24, 28, 32, 36, 42, 48]
