"""Suite-wide test settings."""

import os

# Importing cloud/api/main.py builds the event filter; keep it off NSE's results feed
# (core/events/service.EventFilterService.from_env).
os.environ.setdefault("QUANTOS_EVENTS_FEED", "off")
