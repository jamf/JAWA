#!/usr/bin/python
# encoding: utf-8
import os
import json
from time import sleep
import re
from werkzeug.utils import secure_filename
from flask import (Flask, request, render_template,
                   session, redirect, url_for, escape,
                   send_from_directory, Blueprint, abort)

from crontab import CronTab

from bin import logger
from bin.view_modifiers import response

logthis = logger.setup_child_logger(__name__)
logthis.debug(f'this got logged by {__name__} child')

cron_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'cron.json'))
time_json_file = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'data', 'time.json'))
scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'scripts'))

blueprint = Blueprint('cron', __name__)


@blueprint.route('/cron', methods=['GET', 'POST'])
@response(template_file='cron/home.html')
def cron_home():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.info(f"[{session.get('url')}] {session.get('username').title()} viewed {request.path}")
    with open(cron_json_file, 'r') as fin:
        cron_json = json.load(fin)
    return {"username": session.get('username'), "cron_list": cron_json}


@blueprint.route('/cron/new', methods=['GET', 'POST'])
def new_cron():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.info(f"[{session.get('url')}] {session.get('username').title()} viewed {request.path}")
    days, frequencies, hours = time_definitions()

    if request.method != 'POST':
        return render_template('cron/new.html',
                               cron="cron",
                               frequencies=frequencies,
                               days=days,
                               hours=hours,
                               username=str(escape(session['username'])))

    if ' ' in request.form.get('cron_name'):
        error_message = "Single-string name only."
        return render_template('error.html',
                               error_message=error_message,
                               error="error",
                               username=str(escape(session['username'])))

    cron_description = request.form.get('description')
    cron_name = request.form.get('cron_name')

    if not os.path.isdir(scripts_dir):
        os.mkdir(scripts_dir)
    owd = os.getcwd()
    os.chdir(scripts_dir)
    script = request.files['script']
    if ' ' in script.filename:
        script.filename = script.filename.replace(" ", "-")
    new_script_name = f"cron_{cron_name}_{script.filename}"
    script.save(secure_filename(new_script_name))
    script_file = os.path.join(scripts_dir, new_script_name)

    os.chmod(script_file, mode=0o0755)
    os.chdir(owd)
    frequency = request.form.get('frequency')

    if not os.path.isfile(cron_json_file):
        data = []
        with open(cron_json_file, 'w') as outfile:
            json.dump(data, outfile, indent=4)

    data = json.load(open(cron_json_file))

    for i in data:
        # Mister Krabs
        if str(i['name']) == cron_name:
            error_message = "Name already exists!"
            return render_template('error.html',
                                   error_message=error_message,
                                   error="error",
                                   username=str(escape(session['username'])))
    try:
        cron = CronTab(user=True)
    except IOError as err:
        logthis.info(f"{err}")
        os.remove(script_file)
        return render_template('error.html', error=err, username=session.get('username'))

    if frequency == "everyhour":
        job1 = cron.new(command=script_file, comment=cron_name)
        job1.every().hours()
        job1.minute.on(0)
        cron.write()

    if frequency == "everyday":
        time = request.form.get('daytime')
        job1 = cron.new(command=script_file, comment=cron_name)
        job1.day.every(1)
        job1.hour.on(time)
        job1.minute.on(0)
        cron.write()

    if frequency == "everyweek":
        day = request.form.get('weekday')
        time = request.form.get('weektime')
        job1 = cron.new(command=script_file, comment=cron_name)
        job1.dow.on(day)
        job1.hour.on(time)
        job1.minute.on(0)
        cron.write()

    if frequency == "everymonth":
        day = request.form.get('monthday')
        time = request.form.get('monthtime')
        job1 = cron.new(command=script_file, comment=cron_name)
        job1.day.on(day)
        job1.hour.on(time)
        job1.minute.on(0)
        cron.write()

    if frequency == "custom":
        custom_frequency = request.form.get('customfreq')
        try:
            job1 = cron.new(command=script_file, comment=cron_name)
            job1.setall(f'{custom_frequency}')
            cron.write()
        except (KeyError, ValueError) as err:
            return render_template(
                'error.html',
                error="Custom Crontab Frequency Error",
                error_message=f"The custom job frequency that was presented is invalid:  '{err}'.  Please check your syntax and try again.\nCheck your syntax:  ",
                link=f"https://crontab.guru/#{custom_frequency}",
            )

        frequency = f"Custom [ {custom_frequency} ]"

    data.append({"name": cron_name,
                 "description": cron_description,
                 "frequency": frequency,
                 "script": script_file})

    with open(cron_json_file, 'w') as outfile:
        json.dump(data, outfile, indent=4)
    success_msg = f"{session.get('username')} created {cron_name} to run at the frequency:\n {frequency}."
    logthis.info(f"{success_msg}")

    return render_template('success.html',
                           webhooks="success", success_msg=success_msg,
                           username=str(escape(session['username'])))


def time_definitions():
    with open(time_json_file, 'r+') as fin:
        content = fin.read()
        time_data = json.loads(content)
    days_data = time_data['days']
    hours_data = time_data['hours']
    frequencies_data = time_data['frequencies']
    i = 0
    days = []
    for item in days_data:
        days.append(days_data[i])
        i += 1
    i = 0
    hours = []
    for item in hours_data:
        hours.append(hours_data[i])
        i += 1
    i = 0
    frequencies = []
    for item in frequencies_data:
        frequencies.append(frequencies_data[i])
        i += 1
    return days, frequencies, hours


@blueprint.route('/cron/delete', methods=['GET', 'POST'])
def delete_cron():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.info(f"[{session.get('url')}] {session.get('username')} viewed {request.path}")
    target_job = request.args.get('target_job')
    with open(cron_json_file) as fin:
        cron_json = json.load(fin)
    names = [str(cron_json[i]['name']) for i, item in enumerate(cron_json)]
    if not names:
        return render_template('cron/home.html',
                               username=str(escape(session['username'])))

    if request.method != 'POST':
        return render_template('cron/delete.html',
                               content=names, target_job=target_job,
                               delete_cron="delete_cron",
                               username=str(escape(session['username'])))
    target_job = request.args.get('target_job')

    data = json.load(open(cron_json_file))

    for d in data:
        if d['name'] == target_job:
            script_path = (d['script'])
            new_script_path = f'{script_path}.old'
            if os.path.exists(script_path):
                os.rename(script_path, new_script_path)

    try:
        cron = CronTab(user=True)
    except IOError as err:
        logthis.info(f"{err}")
        return render_template('error.html', error=err, username=session.get('username'))

    for job in cron:
        if job.comment == target_job:
            logthis.info(f"[{session.get('url')}] {session.get('username')} removed cron job {target_job}")
            cron.remove(job)
            cron.write()

    data[:] = [d for d in data if d.get('name') != target_job]

    with open(cron_json_file, 'w') as outfile:
        json.dump(data, outfile, indent=4)
    success_msg = f"{session.get('username')} successfully deleted the Timed Automation: {target_job}."
    return render_template('success.html', success_msg=success_msg,
                           username=str(escape(session['username'])))


@blueprint.route('/cron/edit', methods=['GET', 'POST'])
def edit_cron():
    if 'username' not in session:
        return redirect(url_for('logout', error_title="Session Timed Out", error_message="Please sign in again"))
    logthis.info(f"[{session.get('url')}] {session.get('username')} viewed {request.path}")
    with open(cron_json_file) as fin:
        cron_json = json.load(fin)
    names = []
    name = request.args.get('name')
    for i, item in enumerate(cron_json):
        names.append(str(cron_json[i]['name']))
        if item.get('name') == name:
            description = item.get('description')
    if not name:
        logthis.info(
            '/cron/edit - Warning: No name provided, redirecting to cron home '
        )

        return redirect(url_for('cron.cron_home'))
    logthis.info(f"{session.get('username').title()} checking for job '{name}' in JAWA's crontab")

    try:
        cron = CronTab(user=True)
    except IOError as err:
        logthis.info(f"Error accessing crontab - {err}")
        return render_template('error.html', error=err, username=session.get('username'))

    check_for_name = [True for job in cron if job.comment == name]
    logthis.info(f"Name exists? {check_for_name}")

    if not check_for_name:
        logthis.info(f"JAWA is not aware of any job named {name} in JAWA's crontab")
        return redirect(url_for('cron.cron_home'))

    if not names:
        return render_template('cron/home.html',
                               username=str(escape(session['username'])))

    if request.method != 'POST':
        days, frequencies, hours = time_definitions()
        return render_template('cron/edit.html',
                               content=names, edit_name=name, description=description, days=days, hours=hours,
                               frequencies=frequencies, username=str(escape(session['username'])))

    if ' ' in request.form.get('cron_name'):
        error_message = "Single-string name only."
        return render_template('error.html',
                               error_message=error_message,
                               error="error",
                               username=str(escape(session['username'])))

    button_choice = request.form.get('button_choice')
    if button_choice == 'Delete':
        logthis.info(f"{session.get('username')} is considering deleting a Timed Automation ({name})...")
        return redirect(url_for('cron.delete_cron', target_job=name))

    for each_cron in cron_json:
        if each_cron.get('name') == name:
            new_cron_name = request.form.get('cron_name')
            if not new_cron_name:
                new_cron_name = name
            each_cron['name'] = new_cron_name
            description = request.form.get('description')
            if not description:
                description = each_cron.get('description')
            each_cron['description'] = description
            frequency = request.form.get('frequency')
            frequency_change = False
            if not frequency:
                frequency = each_cron.get('frequency')
            else:
                frequency_change = True
            if frequency == "custom":
                frequency_change = True
                custom_frequency = request.form.get('customfreq')
                each_cron['frequency'] = f"Custom [ {custom_frequency} ]"
            else:
                each_cron['frequency'] = frequency
            script = request.files.get('script')
            if ' ' in script.filename:
                script.filename = script.filename.replace(" ", "-")
            if script.filename:
                if not os.path.isdir(scripts_dir):
                    os.mkdir(scripts_dir)
                owd = os.getcwd()
                os.chdir(scripts_dir)
                new_script_name = f"cron_{new_cron_name}_{script.filename}"
                script.save(secure_filename(new_script_name))
                script_file = os.path.join(scripts_dir, new_script_name)
                os.chmod(script_file, mode=0o0755)
                os.chdir(owd)
                each_cron['script'] = script_file
            else:
                script_file = each_cron.get('script')
        try:
            cron = CronTab(user=True)
        except IOError as err:
            logthis.info(f"Error accessing crontab - {err}")
            return render_template('error.html', error=err, username=session.get('username'))

    for each_job in cron:
        if each_job.comment == name:
            each_job.command = script_file
            each_job.comment = new_cron_name
            if frequency_change:
                if frequency == "everyhour":
                    each_job.every().hours()
                    each_job.minute.on(0)

                if frequency == "everyday":
                    time = request.form.get('daytime')
                    each_job.day.every(1)
                    each_job.hour.on(time)
                    each_job.minute.on(0)

                if frequency == "everyweek":
                    day = request.form.get('weekday')
                    time = request.form.get('weektime')
                    each_job.dow.on(day)
                    each_job.hour.on(time)
                    each_job.minute.on(0)

                if frequency == "everymonth":
                    day = request.form.get('monthday')
                    time = request.form.get('monthtime')
                    each_job.day.on(day)
                    each_job.hour.on(time)
                    each_job.minute.on(0)
                if frequency == "custom":
                    custom_frequency = request.form.get('customfreq')
                    try:
                        each_job.setall(f'{custom_frequency}')
                    except KeyError or ValueError as err:
                        custom_frequency = custom_frequency.replace(" ", "_")
                        return render_template('error.html', error="Custom Crontab Frequency Error",
                                               error_message=f"The custom job frequency that was presented is invalid:  '{err}'.  "
                                                             f"Please check your syntax and try again.\n"
                                                             f"Check your syntax:  ",
                                               link=f"https://crontab.guru/#{custom_frequency}")

            cron.write()

    with open(cron_json_file, 'w') as outfile:
        json.dump(cron_json, outfile, indent=4)
    success_msg = f"{session.get('username')} created {new_cron_name} to run at the frequency:  {frequency}."
    logthis.info(f"{success_msg}")

    return render_template('success.html', success_msg=success_msg,
                           webhooks="success",
                           username=str(escape(session['username'])))
