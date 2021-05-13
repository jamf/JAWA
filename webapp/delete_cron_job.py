#!/usr/bin/python
# encoding: utf-8
import json
import os

from crontab import CronTab
from flask import (request, render_template,
                   session, escape,
                   Blueprint)

cron_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'cron.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

cron_delete = Blueprint('delete_cron', __name__)


@cron_delete.route('/delete_cron', methods=['GET', 'POST'])
def delete_cron():
    exists = os.path.isfile(cron_json_file)
    if not exists:
        return render_template('cron.html',
                               cron="cron",
                               username=str(escape(session['username'])))

    if 'username' in session:
        text = open(cron_json_file, 'r+')
        content = text.read()
        webhook_data = json.loads(content)
        i = 0
        names = []
        for item in webhook_data:
            names.append(str(webhook_data[i]['name']))
            i += 1

        content = names

        if request.method == 'POST':

            timed_job = request.form.get('timed_job')

            data = json.load(open(cron_json_file))

            for d in data:
                if d['name'] == timed_job:
                    script_path = (d['script'])
                    new_script_path = script_path + '.old'
                    os.rename(script_path, new_script_path)

            cron = CronTab(user='root')

            for job in cron:
                if job.comment == timed_job:
                    cron.remove(job)

            data[:] = [d for d in data if d.get('name') != timed_job]

            with open(cron_json_file, 'w') as outfile:
                json.dump(data, outfile)

            return render_template('success.html',
                                   webhooks="success",
                                   username=str(escape(session['username'])))
        else:
            return render_template('delete_cron.html',
                                   content=content,
                                   delete_cron="delete_cron",
                                   username=str(escape(session['username'])))
    else:
        return render_template('home.html',
                               login="false")
