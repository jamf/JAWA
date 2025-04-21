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
from flask import Response, render_template, session, redirect, url_for
from glob import escape
import json
import os
from typing import Union

from bin import logger

logthis = logger.setup_child_logger('jawa', __name__)

server_json_file = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'data', 'server.json')
)


def load_home() -> Union[Response, str]:
    if 'username' in session:
        return redirect(url_for('dashboard'))
    with open(server_json_file, 'r') as fin:
        server_json = json.load(fin)
    if not server_json:
        return render_template('home.html')
    brand = server_json.get('brand')

    if 'jps_url' not in server_json:
        return render_template('home.html', app_name=brand)
    elif server_json['jps_url'] is None:
        return render_template('home.html', app_name=brand)
    elif len(server_json['jps_url']) == 0:
        return render_template('home.html', app_name=brand)
    else:
        if 'alternate_jps' not in server_json:
            return render_template('home.html', app_name=brand)

        if server_json['alternate_jps'] != '':
            return render_template(
                'home.html',
                jps_url=server_json['jps_url'],
                jps_url2=server_json['alternate_jps'],
                welcome='true',
                jsslock='true',
                app_name=brand,
            )

        session['url'] = server_json['jps_url']
        return render_template(
            'home.html',
            jps_url=str(escape(session['url'])),
            welcome='true',
            jsslock='true',
            app_name=brand,
        )
