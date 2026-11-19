# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2026 Jamf.  All rights reserved.
#
#       Redistribution and use in source and binary forms, with or without
#       modification, are permitted provided that the following conditions are met:
#               * Redistributions of source code must retain the above copyright
#                 notice, this list of conditions and the following disclaimer.
#               * Redistributions in binary form must reproduce the above copyright
#                 notice, this list of conditions and the following disclaimer in the
#                 documentation and/or other materials provided with the distribution.
#               * Neither the name of the Jamf nor the names of its contributors may be
#                 used to endorse or promote products derived from this software without
#                 specific prior written permission.
#
#       THIS SOFTWARE IS PROVIDED BY JAMF SOFTWARE, LLC "AS IS" AND ANY
#       EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
#       WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
#       DISCLAIMED. IN NO EVENT SHALL JAMF SOFTWARE, LLC BE LIABLE FOR ANY
#       DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
#       (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
#       LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
#       ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
#       (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
#       SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #

"""Run one timed automation's script and log what it does.

Cron calls this instead of the script itself:

    <venv python> <app dir>/bin/run_cron.py <automation name>

so a timed run's output reaches the JAWA log under the automation's
name, and a non-zero exit is logged as an error and sends the chat
failure alert (if one is set on /setup), the same as a webhook run.
Without it, cron sends the output to the jawa user's local mail, which
nobody reads.

The exit code is the script's own, so cron still sees a failure. The
alert never changes it.
"""

import os
import subprocess
import sys
from typing import List, Optional

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from bin import data_store  # noqa: E402
from bin import failure_alert  # noqa: E402
from bin import logger  # noqa: E402

logthis = logger.setup_child_logger("jawa", "cron_runner")


def run(name: str) -> int:
    """Run timed automation ``name``; return its exit code.

    Any non-zero result, including "no such automation" (1) and "could
    not start" (126), sends the chat failure alert.
    """
    return_code = _run(name)
    if return_code != 0:
        failure_alert.notify_cron_failed(name, return_code)
    return return_code


def _run(name: str) -> int:
    try:
        entry = data_store.get_cron_by_name(name)
    except Exception as err:
        logthis.error(f"{name} - could not read the timed automations: {err}")
        return 1
    script = (entry or {}).get("script")
    if not script:
        logthis.error(f"{name} - no timed automation with this name")
        return 1
    try:
        proc = subprocess.Popen(
            [script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as err:
        logthis.error(f"{name} - could not run {script}: {err}")
        return 126
    for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line:
            logthis.info(f"{name} - {line}")
    return_code = proc.wait()
    if return_code != 0:
        logthis.error(
            f"Script execution failed for {name} with exit code {return_code}"
        )
    return return_code


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: run_cron.py <automation name>", file=sys.stderr)
        return 2
    return run(args[0])


if __name__ == "__main__":
    sys.exit(main())
