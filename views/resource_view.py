# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2024 Jamf.  All rights reserved.
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

import json
import os
from datetime import datetime
from typing import Any, Dict, Tuple, Union

from flask import (
    Blueprint,
    Response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from markupsafe import escape
from werkzeug.utils import secure_filename

from bin import logger
from bin.view_modifiers import response

logthis = logger.setup_child_logger("jawa", __name__)

log_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "jawa.log")
)
server_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "server.json")
)
resources_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "resources")
)
files_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "resources", "files")
)
img_dir = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "static", "img")
)

blueprint = Blueprint("resources_view", __name__, template_folder="templates")

_SIZE_UNITS = ("KB", "MB", "GB", "TB")


def _format_size(num_bytes: int) -> str:
    """Render a byte count the way an admin reads it.

    Bytes stay whole below 1 KB so a 40-byte script does not read
    "0.0 KB". Above that, one decimal place is enough to tell a 200 KB
    plist from a 2 MB installer -- which is the decision this column
    exists to support.
    """
    if num_bytes < 1024:
        return f"{num_bytes} B"
    size = float(num_bytes)
    for unit in _SIZE_UNITS:
        size /= 1024
        if size < 1024 or unit == _SIZE_UNITS[-1]:
            return f"{size:.1f} {unit}"
    return f"{size:.1f} {_SIZE_UNITS[-1]}"


def _format_type(filename: str) -> str:
    """The extension as a short uppercase label, or a dash if there is none.

    A dash rather than an empty cell or a Python None: the column is
    scanned down, so every row needs something in it.
    """
    extension = os.path.splitext(filename)[1].lstrip(".")
    return extension.upper() if extension else "—"


@blueprint.route("/resources/files", methods=["GET", "POST"])
def files() -> Union[Response, Tuple[str, int]]:
    if "username" not in session:
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Session Timed Out",
                error_message="Please sign in again",
            )
        )
    target_file = request.args.get("target_file")
    if target_file:
        target_file = secure_filename(target_file)
    button_choice = request.args.get("button_choice")
    if button_choice:
        button_choice = escape(button_choice)
    if target_file:
        target_file_dir = os.path.dirname(
            os.path.abspath(os.path.join(files_dir, target_file))
        )
        target_file_path = os.path.abspath(
            os.path.join(files_dir, target_file)
        )
        if button_choice == "Download":
            logthis.info(
                f"[{session.get('url')}] {session.get('username')} downloading file: {target_file}."
            )
            if target_file_dir != files_dir:
                logthis.warning(
                    f"WARNING: [{session.get('url')}] {session.get('username')} attempted to download a file from a forbidden path: {target_file_path}."
                )
                return (
                    "Forbidden:  you are not allowed to download files from alternative paths.",
                    403,
                )
            return send_file(f"{target_file_path}", as_attachment=True)
        elif button_choice == "Delete":
            logthis.debug(
                f"[{session.get('url')}] {session.get('username')} is considering deleting a Resource file ({target_file_path})..."
            )
            return redirect(
                url_for("resources_view.delete_file", target_file=target_file)
            )

    if request.method == "POST":
        logthis.info(
            f"[{session.get('url')}] {session.get('username')} {request.path} {request.method}"
        )
        upload_files_list = request.files.getlist("upload")
        for each_upload in upload_files_list:
            if " " in each_upload.filename:
                each_upload.filename = each_upload.filename.replace(" ", "-")
            logthis.info(
                f"[{session.get('url')}] {session.get('username')} uploaded {each_upload.filename}."
            )
            each_upload.save(
                os.path.join(files_dir, secure_filename(each_upload.filename))
            )
    logthis.info(
        f"[{session.get('url')}] {session.get('username')} {request.path} {request.method}"
    )
    # Sorted, and filtered by comprehension rather than by removing from
    # the list being iterated -- that shifts the next element past the
    # cursor, so two adjacent dotfiles leaked the second one into the page.
    file_list = sorted(
        each for each in os.listdir(files_dir) if not each.startswith(".")
    )
    files_list = []
    for each_file in file_list:
        each_path = os.path.join(files_dir, each_file)
        try:
            mtime = os.path.getmtime(each_path)
            size = os.path.getsize(each_path)
        except OSError:
            # listdir-then-stat is a race: a second admin deleting a file
            # mid-request must not take the whole listing down with it.
            logthis.debug(
                f"Skipping {each_file}: vanished while listing resources."
            )
            continue
        pretty_mtime = datetime.fromtimestamp(mtime).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        files_list.append(
            {
                "name": each_file,
                "mtime": pretty_mtime,
                "size": _format_size(size),
                "type": _format_type(each_file),
            }
        )
    return render_template(
        "resources/files.html",
        username=session.get("username"),
        files_repo=files_dir,
        files=files_list,
    )


@blueprint.route("/resources/delete.html", methods=["GET", "POST"])
def delete_file() -> Union[Response, Tuple[str, int]]:
    target_file = request.args.get("target_file")
    if target_file:
        target_file = secure_filename(target_file)
    if "username" not in session:
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Session Timed Out",
                error_message="Please sign in again",
            )
        )
    if request.method != "POST":
        return render_template(
            "resources/delete.html",
            target_file=target_file,
            username=str(escape(session.get("username"))),
        )
    if not target_file:
        logthis.warning(
            f"[{session.get('url')}] {session.get('username')} "
            f"attempted a file deletion with no file selected."
        )
        return redirect(
            url_for(
                "error",
                error="No file selected",
                error_message="Select a file to delete.",
            )
        )

    target_file_dir = os.path.dirname(
        os.path.abspath(os.path.join(files_dir, target_file))
    )
    target_file_path = os.path.abspath(
        os.path.join(files_dir, target_file)
    )

    if target_file_dir != files_dir:
        logthis.warning(
            f"WARNING: [{session.get('url')}] {session.get('username')} attempted to delete a file from a forbidden path: {target_file_path}."
        )
        return (
            "Forbidden:  you are not allowed to download files from alternative paths.",
            403,
        )
    logthis.info(
        f"[{session.get('url')}] {session.get('username')} deleting file: {target_file}."
    )
    if os.path.exists(os.path.join(files_dir, target_file)):
        try:
            os.remove(os.path.join(files_dir, target_file))
            logthis.info(
                f"[{session.get('url')}] {session.get('username')} successfully deleted the Resource file: {target_file}."
            )
            return redirect(url_for("resources_view.files"))
        except Exception as err:
            logthis.error(
                f"[{session.get('url')}] {session.get('username')} failed to delete Resource file {target_file}: {err}"
            )
            error = "Error deleting file."
            error_message = f"Permission denied or file in use: {target_file}. {err}"
            return render_template(
                "error.html",
                error=error,
                error_message=error_message,
                username=str(escape(session["username"])),
            )
    else:
        logthis.error(
            f"[{session.get('url')}] {session.get('username')} attempted to delete non-existent file: {target_file}"
        )
        error = "Error deleting file."
        error_message = f"File does not exist {target_file}."
        return render_template(
            "error.html",
            error=error,
            error_message=error_message,
            username=str(escape(session["username"])),
        )


@blueprint.route("/branding", methods=["GET", "POST"])
@response(template_file="setup/branding.html")
def rebrand() -> Union[Response, Dict[str, Any]]:
    if "username" not in session:
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Session Timed Out",
                error_message="Please sign in again",
            )
        )
    if not os.path.isfile(server_file):
        with open(server_file, "w") as fout:
            json.dump({}, fout)
    with open(server_file) as fin:
        server_json = json.load(fin)
    brand = server_json.get("brand")
    if request.method == "POST":
        upload_files_list = request.files.getlist("upload")
        new_name = request.form.get("new_name")
        if new_name:
            server_json["brand"] = new_name
            brand = new_name

            with open(server_file, "w") as fout:
                json.dump(server_json, fout, indent=4)
        if upload_files_list:
            target_file = upload_files_list[0]
            if target_file:
                os.rename(
                    f"{img_dir}/jawa_icon.png",
                    f"{img_dir}/old_jawa_icon_{datetime.now()}.png",
                )
                target_file.save(os.path.join(img_dir, "jawa_icon.png"))
                return redirect(url_for("resources_view.rebrand"))
            return {"username": session.get("username"), "app_name": brand}
        return {"username": session.get("username"), "app_name": brand}

    return {"username": session.get("username"), "app_name": brand}


@blueprint.route("/python")
@response(template_file="resources/python.html")
def python() -> Union[Response, Dict[str, Any]]:
    if "username" not in session:
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Session Timed Out",
                error_message="Please sign in again",
            )
        )
    return {"username": session.get("username")}


@blueprint.route("/bash")
@response(template_file="resources/bash.html")
def bash() -> Union[Response, Dict[str, Any]]:
    if "username" not in session:
        return redirect(
            url_for(
                "home_view.logout",
                error_title="Session Timed Out",
                error_message="Please sign in again",
            )
        )
    return {"username": session.get("username")}
