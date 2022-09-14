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
        logthis.info("Could not get a token using session credentials.  Logging out.")
        return redirect(
            url_for('home_view.logout', error_title="Error Fetching API Token", error_message="Please sign in again"))


def validate_token(expires):
    time_to_expire = datetime.strptime(expires, '%Y-%m-%dT%H:%M:%S.%f%z') - datetime.strptime(
        str(datetime.now(timezone.utc)), '%Y-%m-%d %H:%M:%S.%f%z')
    if time_to_expire > timedelta(0):
        return True
    else:
        logthis.info(f"API token expired ({time_to_expire}). Attempting to fetch new token...")
        return False
