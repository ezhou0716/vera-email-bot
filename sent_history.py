"""Sent-history tracker for Vera Email Bot.

Reads/writes a local ``sent_history.json`` file so both the GUI and CLI can
flag leads that have already been contacted.
"""

import json
import os
from datetime import datetime

HISTORY_FILE = "sent_history.json"


def load_history() -> dict:
    """Load sent_history.json → dict[email → {last_sent, send_count, subject}].

    Returns an empty dict if the file doesn't exist or is malformed.
    """
    if not os.path.exists(HISTORY_FILE):
        return {}
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_history(history: dict) -> None:
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def record_sent(email: str, subject: str) -> None:
    """Record (or update) an entry after a successful send."""
    history = load_history()
    entry = history.get(email, {"send_count": 0})
    entry["last_sent"] = datetime.now().isoformat(timespec="seconds")
    entry["send_count"] = entry.get("send_count", 0) + 1
    entry["subject"] = subject
    history[email] = entry
    _save_history(history)


def was_previously_contacted(email: str, history: dict | None = None) -> tuple[bool, dict | None]:
    """Check whether *email* appears in the sent history.

    Parameters
    ----------
    email : str
        The email address to look up.
    history : dict, optional
        A pre-loaded history dict.  If *None*, the file is read from disk.

    Returns
    -------
    (bool, info_dict_or_None)
    """
    if history is None:
        history = load_history()
    info = history.get(email)
    if info:
        return True, info
    return False, None
