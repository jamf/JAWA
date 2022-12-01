# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# Copyright (c) 2022 Jamf.  All rights reserved.
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

from flask import (Blueprint, escape, redirect, render_template,
                   request, send_file, session, url_for)
from werkzeug.utils import secure_filename

from bin import logger
from bin.view_modifiers import response

logthis = logger.setup_child_logger('jawa', __name__)

log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jawa.log'))
server_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))
resources_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources'))
files_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'files'))
img_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'static', 'img'))

blueprint = Blueprint('resources_view', __name__, template_folder='templates')


@blueprint.route('/resources/files', methods=['GET', 'POST'])
def files():
    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    target_file = request.args.get('target_file')
    button_choice = request.args.get('button_choice')
    if target_file:
        target_file_dir = os.path.dirname(os.path.abspath(os.path.join(files_dir, target_file)))
        target_file_path = os.path.abspath(os.path.join(files_dir, target_file))
        if button_choice == "Download":
            logthis.info(f"[{session.get('url')}] {session.get('username')} downloading file: {target_file}.")
            if target_file_dir != files_dir:
                logthis.info(
                    f"WARNING: [{session.get('url')}] {session.get('username')} attempted to download a file from a forbidden path: {target_file_path}.")
                return "Forbidden:  you are not allowed to download files from alternative paths.", 403
            return send_file(f'{target_file_path}', as_attachment=True)
        elif button_choice == "Delete":
            logthis.debug(
                f"[{session.get('url')}] {session.get('username')} is considering deleting a Resource file ({target_file_path})...")
            return redirect(url_for('resources_view.delete_file', target_file=target_file))

    if request.method == "POST":
        logthis.info(f"[{session.get('url')}] {session.get('username')} {request.path} {request.method}")
        upload_files_list = request.files.getlist('upload')
        for each_upload in upload_files_list:
            if ' ' in each_upload.filename:
                each_upload.filename = each_upload.filename.replace(" ", "-")
            logthis.info(f"[{session.get('url')}] {session.get('username')} uploaded {each_upload.filename}.")
            each_upload.save(os.path.join(files_dir, secure_filename(each_upload.filename)))
    logthis.info(f"[{session.get('url')}] {session.get('username')} {request.path} {request.method}")
    file_list = os.listdir(files_dir)
    for file in file_list:
        if file[0] == '.':
            file_list.remove(file)
    files_list = []
    for each_file in file_list:
        mtime = os.path.getmtime(os.path.join(files_dir, each_file))
        pretty_mtime = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        files_list.append({"name": each_file, "mtime": pretty_mtime})
    return render_template('resources/files.html', username=session.get('username'), files_repo=files_dir,
                           files=files_list)


@blueprint.route('/resources/delete.html', methods=['GET', 'POST'])
def delete_file():
    target_file = request.args.get('target_file')
    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    if request.method != 'POST':
        return render_template('resources/delete.html',
                               target_file=target_file, username=str(escape(session.get('username'))))
    if target_file:
        target_file_dir = os.path.dirname(os.path.abspath(os.path.join(files_dir, target_file)))
        target_file_path = os.path.abspath(os.path.join(files_dir, target_file))

    if target_file_dir != files_dir:
        logthis.info(
            f"WARNING: [{session.get('url')}] {session.get('username')} attempted to delete a file from a forbidden path: {target_file_path}.")
        return "Forbidden:  you are not allowed to download files from alternative paths.", 403
    logthis.info(f"[{session.get('url')}] {session.get('username')} deleting file: {target_file}.")
    if os.path.exists(os.path.join(files_dir, target_file)):
        os.remove(os.path.join(files_dir, target_file))
        logthis.info(f"[{session.get('url')}] {session.get('username')} successfully deleted the Resource file: {target_file}.")
        return redirect(url_for('resources_view.files'))
    else:
        error = f"Error deleting file."
        error_message = f"File does not exist {target_file}."
        return render_template('error.html', error=error, error_message=error_message,
                               username=str(escape(session['username'])))


@blueprint.route('/branding', methods=['GET', 'POST'])
@response(template_file='setup/branding.html')
def rebrand():
    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    if not os.path.isfile(server_file):
        with open(server_file, "w") as fout:
            json.dump({}, fout)
    with open(server_file) as fin:
        server_json = json.load(fin)
    brand = server_json.get('brand')
    if request.method == "POST":
        upload_files_list = request.files.getlist('upload')
        new_name = request.form.get('new_name')
        if new_name:
            server_json['brand'] = new_name
            brand = new_name

            with open(server_file, 'w') as fout:
                json.dump(server_json, fout, indent=4)
        if upload_files_list:
            target_file = upload_files_list[0]
            if target_file:
                os.rename(f"{img_dir}/jawa_icon.png", f"{img_dir}/old_jawa_icon_{datetime.now()}.png")
                target_file.save(os.path.join(img_dir, "jawa_icon.png"))
                return redirect(url_for('resources_view.rebrand'))
            return {'username': session.get('username'), "app_name": brand}
        return {'username': session.get('username'), "app_name": brand}

    return {'username': session.get('username'), "app_name": brand}


@blueprint.route("/python")
@response(template_file="resources/python.html")
def python():
    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    return {"username": session.get('username')}


@blueprint.route("/bash")
@response(template_file="resources/bash.html")
def bash():
    if 'username' not in session:
        return redirect(
            url_for('home_view.logout', error_title="Session Timed Out", error_message="Please sign in again"))
    return {"username": session.get('username')}
