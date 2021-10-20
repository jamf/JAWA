import json
import os
from glob import escape

from flask import render_template, session, redirect, url_for

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))


def load_home():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    with open(server_json_file, "r") as fin:
        server_json = json.load(fin)
    if not server_json:
        return render_template('home.html')
    brand = server_json.get("brand")

    if 'jps_url' not in server_json:
        return render_template('home.html', app_name=brand)
    elif server_json['jps_url'] is None:
        return render_template('home.html', app_name=brand)
    elif len(server_json['jps_url']) == 0:
        return render_template('home.html', app_name=brand)
    else:
        if 'alternate_jps' not in server_json:
            return render_template('home.html', app_name=brand)

        if server_json['alternate_jps'] != "":
            return render_template('home.html',
                                   jps_url=server_json['jps_url'],
                                   jps_url2=server_json['alternate_jps'],
                                   welcome="true", jsslock="true", app_name=brand)

        session['url'] = server_json['jps_url']
        return render_template('home.html',
                               jps_url=str(escape(session['url'])),
                               welcome="true", jsslock="true", app_name=brand)
