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

import getpass
import os
import shlex
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from crontab import CronTab

from bin import logger
from bin.data_store import (
    get_all_crons,
    get_time_data,
    save_script,
    save_all_crons,
    retire_script,
)
from views._type_handlers.base import AutomationError, AutomationHandler

logthis = logger.setup_child_logger("jawa", "cron_handler")


def _get_crontab() -> CronTab:
    try:
        return CronTab(user=True)
    except IOError as err:
        logthis.error(
            f"Error accessing crontab for {getpass.getuser()} - {err}"
        )
        raise AutomationError("Crontab Error", str(err))


RUN_CRON = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "bin", "run_cron.py")
)


def cron_command(name: str) -> str:
    """The crontab command for timed automation ``name``.

    Cron runs bin/run_cron.py under JAWA's own interpreter (the venv the
    service runs in), which runs the script and writes its output and
    exit status to the JAWA log.
    """
    return " ".join(
        shlex.quote(part) for part in (sys.executable, RUN_CRON, name)
    )


def migrate_cron_commands() -> int:
    """Point existing JAWA crontab lines at bin/run_cron.py.

    Lines written before the runner existed call the script directly, so
    their output never reaches the JAWA log. A line is JAWA's when its
    comment is the name of an entry in cron.json. Returns the number of
    lines changed. Never raises: a host without a usable crontab must
    still start.
    """
    try:
        names = {entry.get("name") for entry in get_all_crons()}
        cron = CronTab(user=True)
        changed = 0
        for job in cron:
            if job.comment in names:
                command = cron_command(job.comment)
                if job.command != command:
                    job.command = command
                    changed += 1
        if changed:
            cron.write()
            logthis.info(
                f"Updated {changed} timed automation(s) to log through "
                f"run_cron.py"
            )
        return changed
    except Exception as err:
        logthis.warning(f"Could not update timed automation commands: {err}")
        return 0


PRESET_FREQUENCIES = ("everyhour", "everyday", "everyweek", "everymonth")


def _hour_label(hour_id: Any) -> str:
    """'2:00 AM' for hour id '2', using the labels the form shows."""
    for hour in get_time_data().get("hours", []):
        if str(hour.get("id")) == str(hour_id):
            return hour.get("value", "")
    return f"{hour_id}:00" if str(hour_id).isdigit() else str(hour_id)


def _day_label(day_cron: Any) -> str:
    """'Monday' for the weekday code 'MON'."""
    for day in get_time_data().get("days", []):
        if day.get("cron") == day_cron or str(day.get("id")) == str(day_cron):
            return day.get("value", "")
    return str(day_cron)


def _custom_label(expression: str) -> str:
    return f"Custom [ {expression} ]"


def _is_preset(stored: str) -> bool:
    """True for an old entry that saved only the form's preset value."""
    return not stored or stored in PRESET_FREQUENCIES or stored == "custom"


def _apply_frequency(job: Any, frequency: str, form: Any) -> str:
    """Apply the chosen frequency to a cron job.

    Returns a readable label such as "Every day at 2:00 AM".
    """
    if frequency == "everyhour":
        job.every().hours()
        job.minute.on(0)
        return "Every hour, on the hour"
    elif frequency == "everyday":
        time_val = form.get("daytime")
        job.day.every(1)
        job.hour.on(time_val)
        job.minute.on(0)
        return f"Every day at {_hour_label(time_val)}"
    elif frequency == "everyweek":
        day = form.get("weekday")
        time_val = form.get("weektime")
        job.dow.on(day)
        job.hour.on(time_val)
        job.minute.on(0)
        return f"Every {_day_label(day)} at {_hour_label(time_val)}"
    elif frequency == "everymonth":
        day = form.get("monthday")
        time_val = form.get("monthtime")
        job.day.on(day)
        job.hour.on(time_val)
        job.minute.on(0)
        return f"On day {day} of every month at {_hour_label(time_val)}"
    elif frequency == "custom":
        custom_freq = form.get("customfreq", "")
        try:
            job.setall(f"{custom_freq}")
        except (KeyError, ValueError) as err:
            safe_freq = custom_freq.replace(" ", "_")
            raise AutomationError(
                "Custom Crontab Frequency Error",
                f"The custom job frequency that was presented is invalid: "
                f"'{err}'. Please check your syntax and try again.\n"
                f"Check your syntax:  ",
                link=f"https://crontab.guru/#{safe_freq}",
            )
        return _custom_label(custom_freq)
    return frequency


class CronHandler(AutomationHandler):
    tag = "cron"
    display_name = "Timed Automation"
    summary = "Runs a script on a schedule."
    badge_class = "badge-observability"
    icon = "timed_automation.png"
    supports_edit = True
    supports_auth = False

    def get_create_context(self, session_data: Dict) -> Dict[str, Any]:
        time_data = get_time_data()
        return {
            "frequencies": time_data["frequencies"],
            "days": time_data["days"],
            "hours": time_data["hours"],
        }

    def process_create(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
    ) -> Dict[str, Any]:
        cron_name = form.get("cron_name", "")
        description = form.get("description", "")
        frequency = form.get("frequency", "")

        if not cron_name:
            raise AutomationError("Error", "Automation name is required.")
        if " " in cron_name:
            raise AutomationError("Error", "Single-string name only.")

        # Save script
        script_file = files.get("script")
        if not script_file or not script_file.filename:
            raise AutomationError("Error", "A script file is required.")
        script_path = save_script(script_file, f"cron_{cron_name}", "_")

        # Create crontab entry
        cron = _get_crontab()
        job = cron.new(command=cron_command(cron_name), comment=cron_name)
        display_freq = _apply_frequency(job, frequency, form)
        cron.write()

        entry = {
            "name": cron_name,
            "description": description,
            "frequency": display_freq,
            "script": script_path,
        }

        success_msg = (
            f"[{session_data.get('url')}] "
            f"{session_data.get('username')} created {cron_name} "
            f"to run at the frequency:\n {display_freq}."
        )
        logthis.info(success_msg)

        return {
            "entry": entry,
            "success_msg": success_msg,
        }

    def process_edit(
        self,
        form: Any,
        files: Any,
        session_data: Dict,
        existing: Dict,
        all_items: Any,
    ) -> Dict[str, Any]:
        name = existing["name"]
        new_name = form.get("cron_name") or name
        description = form.get("description") or existing.get("description")
        frequency = form.get("frequency")
        frequency_change = bool(frequency)

        if not frequency:
            frequency = existing.get("frequency")

        # Update the entry
        existing["name"] = new_name
        existing["description"] = description

        # Handle script upload
        if files.get("script") and files["script"].filename:
            script_path = save_script(files["script"], f"cron_{new_name}", "_")
            existing["script"] = script_path

        # Update crontab
        cron = _get_crontab()
        display_freq = frequency

        for job in cron:
            if job.comment == name:
                job.command = cron_command(new_name)
                job.comment = new_name
                if frequency_change:
                    display_freq = _apply_frequency(job, frequency, form)
                cron.write()
                break

        if frequency == "custom":
            custom_freq = form.get("customfreq", "")
            existing["frequency"] = _custom_label(custom_freq)
        else:
            existing["frequency"] = display_freq

        save_all_crons(all_items)

        success_msg = (
            f"[{session_data.get('url')}] "
            f"{session_data.get('username')} edited {new_name} "
            f"to run at the frequency:  {display_freq}."
        )
        logthis.info(success_msg)

        return {
            "success_msg": success_msg,
        }

    def process_delete(
        self, automation: Dict, session_data: Dict
    ) -> Optional[str]:
        name = automation["name"]
        script_path = automation.get("script", "")
        retire_script(script_path)

        cron = _get_crontab()
        for job in cron:
            if job.comment == name:
                logthis.info(
                    f"[{session_data.get('url')}] "
                    f"{session_data.get('username')} removed cron job "
                    f"{name}"
                )
                cron.remove(job)
                cron.write()
                break
        return None

    def get_detail_fields(self, automation: Dict) -> List[Tuple[str, str]]:
        fields = [("Automation name", automation.get("name", ""))]
        fields.extend(self._schedule_fields(automation))
        fields.extend(
            [
                ("Script path", automation.get("script", "")),
                ("Description", automation.get("description", "")),
            ]
        )
        return fields

    def _schedule_fields(self, automation: Dict) -> List[Tuple[str, str]]:
        """Schedule and next run, read from the crontab that really runs it.

        The stored label is what the admin chose; the crontab line is
        what executes, so a missing line means the job is not running.
        """
        stored = automation.get("frequency", "") or ""
        try:
            cron = _get_crontab()
        except AutomationError:
            return [("Schedule", stored or "Unknown (crontab unreadable)")]
        job = next(
            (j for j in cron if j.comment == automation.get("name")), None
        )
        if job is None:
            return [
                (
                    "Schedule",
                    "Not scheduled: no crontab entry for this job",
                )
            ]
        label = str(job.slices) if _is_preset(stored) else stored
        fields = [("Schedule", label)]
        try:
            next_run = job.schedule(date_from=datetime.now()).get_next()
            fields.append(
                (
                    "Next run",
                    f"{next_run:%a} {next_run.day} {next_run:%b}, "
                    f"{next_run.hour % 12 or 12}:{next_run:%M %p}"
                    " (server time)",
                )
            )
        except Exception as err:  # croniter missing or odd expression
            logthis.warning(
                f"Could not work out the next run of "
                f"{automation.get('name')}: {err}"
            )
        return fields
