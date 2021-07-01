import json
import os
from glob import escape

from flask import render_template, session

server_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json'))


def load_home():
    if not os.path.isfile(server_json_file):
        return render_template('home.html')
    with open(server_json_file, "r") as fin:
        server_json = json.load(fin)
    if not server_json:
        return render_template('home.html')
    else:
        with open(server_json_file) as json_file:
            server_json = json.load(json_file)
        print(server_json)

        if not 'jps_url' in server_json:
            return render_template('home.html')
        elif server_json['jps_url'] == None:
            return render_template('home.html')
        elif len(server_json['jps_url']) == 0:
            return render_template('home.html')
        else:
            if not 'alternate_jps' in server_json:
                return render_template('home.html')

            if server_json['alternate_jps'] != "":
                return render_template('home.html',
                                       jps_url=server_json['jps_url'],
                                       jps_url2=server_json['alternate_jps'],
                                       welcome="true", jsslock="true")

            session['url'] = server_json['jps_url']
            return render_template('home.html',
                                   jps_url=str(escape(session['url'])),
                                   welcome="true", jsslock="true")