import os
import json


STATE_FILE = "data/state.json"


DEFAULT_STATE = {
    "posted_announcements": []
}


def ensure_state_file():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(STATE_FILE):
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_STATE, f, indent=2)