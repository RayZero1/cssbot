import os
import json

STATE_FILE = "data/state.json"
TICKETS_FILE = "data/tickets.json"

DEFAULT_STATE = {
    "posted_announcements": []
}

DEFAULT_TICKETS = {
    "last_ticket_id": 0,
    "tickets": {},
}

def ensure_state_file():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STATE, f, indent=2)

    if not os.path.exists(TICKETS_FILE):
        with open(TICKETS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_TICKETS, f, indent=2)