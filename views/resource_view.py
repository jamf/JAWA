from datetime import datetime
from flask import current_app, session, redirect, url_for, render_template, Flask, Blueprint, send_file, request
from main import jawa_logger
import os
from werkzeug.utils import secure_filename

from bin.load_home import load_home
from bin.view_modifiers import response

log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'jawa.log'))
resources_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources'))
files_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'resources', 'files'))

blueprint = Blueprint('resources_view', __name__, template_folder='templates')


@blueprint.route('/resources/files', methods=['GET', 'POST'])
def files_download():
    if not 'username' in session:
        return load_home()
    target_file = request.args.get('target_file')
    if target_file:
        return send_file(f'{files_dir}/{target_file}', as_attachment=True)
    if request.method == "POST":
        print(request)
        print("POST")
        upload_files_list = request.files.getlist('upload')
        print(upload_files_list)
        for each_upload in upload_files_list:

            print(each_upload)
            if ' ' in each_upload.filename:
                each_upload.filename = each_upload.filename.replace(" ", "-")
            each_upload.save(os.path.join(files_dir, secure_filename(each_upload.filename)))
    jawa_logger().info(f"/resources/files.html accessed by {session.get('username') or 'nobody'}")
    files = os.listdir(files_dir)
    for file in files:
        if file[0] == '.':
            files.remove(file)
    print(files)
    files_list = []
    for each_file in files:
        mtime = os.path.getmtime(os.path.join(files_dir, each_file))
        pretty_mtime = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S')
        files_list.append({"name": each_file, "mtime": pretty_mtime})
    print(files_list)
    return render_template('resources/files.html', username=session.get('username'), files_repo=files_dir,
                           files=files_list)
