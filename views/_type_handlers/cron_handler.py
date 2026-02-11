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
from typing import Any, Dict, List, Optional, Tuple

from crontab import CronTab

from bin import logger
from bin.data_store import (
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
        logthis.info(
            f"Error accessing crontab for {getpass.getuser()} - {err}"
        )
        raise AutomationError("Crontab Error", str(err))


def _apply_frequency(job: Any, frequency: str, form: Any) -> str:
    """Apply the chosen frequency to a cron job. Returns display frequency."""
    if frequency == "everyhour":
        job.every().hours()
        job.minute.on(0)
    elif frequency == "everyday":
        time_val = form.get("daytime")
        job.day.every(1)
        job.hour.on(time_val)
        job.minute.on(0)
    elif frequency == "everyweek":
        day = form.get("weekday")
        time_val = form.get("weektime")
        job.dow.on(day)
        job.hour.on(time_val)
        job.minute.on(0)
    elif frequency == "everymonth":
        day = form.get("monthday")
        time_val = form.get("monthtime")
        job.day.on(day)
        job.hour.on(time_val)
        job.minute.on(0)
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
        return f"Custom [ {custom_freq} ]"
    return frequency


class CronHandler(AutomationHandler):
    tag = "cron"
    display_name = "Timed Automation"
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
        job = cron.new(command=script_path, comment=cron_name)
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
        else:
            script_path = existing.get("script", "")

        # Update crontab
        cron = _get_crontab()
        display_freq = frequency

        for job in cron:
            if job.comment == name:
                job.command = script_path
                job.comment = new_name
                if frequency_change:
                    display_freq = _apply_frequency(job, frequency, form)
                cron.write()
                break

        if frequency == "custom":
            custom_freq = form.get("customfreq", "")
            existing["frequency"] = f"Custom [ {custom_freq} ]"
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
        return [
            ("Automation name", automation.get("name", "")),
            ("Frequency", automation.get("frequency", "")),
            ("Script path", automation.get("script", "")),
            ("Description", automation.get("description", "")),
        ]
