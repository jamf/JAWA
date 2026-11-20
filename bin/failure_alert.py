"""Chat failure alerts, shared by webhook runs and timed (cron) runs.

The webhook receiver sends from a background thread with an in-memory
rate limit. ``bin/run_cron.py`` is a new process per run, so it sends
synchronously and keeps its rate limit in a small JSON file instead.
Nothing here raises to its caller.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Optional

import requests

from bin import data_store
from bin import logger

logthis = logger.setup_child_logger("jawa", "failure_alert")

# At most one alert per automation in this window.
ALERT_INTERVAL_SECONDS = 15 * 60
POST_TIMEOUT_SECONDS = 10


def alert_url(server_file: Optional[str] = None) -> str:
    """The chat webhook set on /setup, or "" when none is configured."""
    path = server_file or data_store.SERVER_FILE
    try:
        with open(path, "r") as fin:
            data = json.load(fin)
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("failure_alert_url") or "").strip()


def alert_text(name: str, code: Any) -> str:
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    return f"JAWA: {name} failed (exit {code}) at {stamp}"


def post(url: str, text: str, log: Optional[logging.Logger] = None) -> None:
    """POST the alert. Never raises.

    Logs the exception type only: the requests error text can carry the
    URL, and the URL is a credential.
    """
    log = log or logthis
    try:
        resp = requests.post(
            url, json={"text": text}, timeout=POST_TIMEOUT_SECONDS
        )
        if resp.status_code >= 400:
            log.warning(
                f"Failure alert was refused with HTTP {resp.status_code}."
            )
    except Exception as err:
        log.warning(f"Failure alert could not be sent ({type(err).__name__}).")


# --- Timed (cron) runs ----------------------------------------------------


def notify_cron_failed(name: str, code: Any) -> None:
    """Send the failure alert for a timed run, synchronously. Never raises.

    Each cron run is its own process, so the per-name rate limit is kept
    on disk by ``data_store.claim_cron_alert``.
    """
    try:
        url = alert_url()
        if not url:
            return
        try:
            allowed = data_store.claim_cron_alert(
                name, time.time(), ALERT_INTERVAL_SECONDS
            )
        except Exception as err:
            # Could not read or save the last alert time: send anyway,
            # since a missed alert is worse than an extra one.
            logthis.warning(
                f"Failure alert time for {name} was not saved "
                f"({type(err).__name__})."
            )
            allowed = True
        if allowed:
            post(url, alert_text(name, code))
    except Exception as alert_err:
        logthis.warning(f"Failure alert for {name} was not sent: {alert_err}")
