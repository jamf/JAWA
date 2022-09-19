from datetime import datetime, timezone, timedelta
from flask import session, redirect, url_for
import requests
import time

from bin import logger

logthis = logger.setup_child_logger('jawa', __name__)


def get_token():
    try:
        resp = requests.post(f"{session['url']}/api/v1/auth/token",
                             headers={'Authorization': f"Basic {session['b64_auth'].decode()}"})
        data = resp.json()
        session['token'] = data.get('token')
        session['expires'] = data.get('expires')
    except Exception as err:
        logthis.info("[{session.get('url')}] Could not get a token using session credentials.  Logging out.")
        return redirect(
            url_for('home_view.logout', error_title="Error Fetching API Token", error_message="Please sign in again"))


def validate_token(expires):
    time_to_expire = datetime.strptime(expires, '%Y-%m-%dT%H:%M:%S.%f%z') - datetime.strptime(
        str(datetime.now(timezone.utc)), '%Y-%m-%d %H:%M:%S.%f%z')
    if time_to_expire > timedelta(0):
        return True
    else:
        logthis.info(f"[{session.get('url')}] API token expired ({time_to_expire}). Attempting to fetch new token...")
        return False


def invalidate_token():
    if not session.get('token'):
        return
    try:
        resp = requests.post(f"{session['url']}/api/v1/auth/invalidate-token",
                             headers={'Authorization': f"Bearer {session.get('token')}"})
    except Exception as err:
        logthis.info(f"[{session.get('url')}] Error accessing Jamf Pro API endpoint for token invalidation. {err}")
        return
    if resp.status_code == 204:
        logthis.info(f"[{session.get('url')}] Successfully invalidated token for logout.")
    elif resp.status_code == 401:
        logthis.info(f"[{session.get('url')}] Token is already invalid.  Logging out.")
    else:
        logthis.info(f"[{session.get('url')}] An unknown error occurred when invalidating the token.")
