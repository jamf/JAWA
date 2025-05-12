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
import sys

try:
    backup_dir = sys.argv[1]
    old_server_json_path = f"{backup_dir}/v2/server.json"
    new_server_json_path = f"{backup_dir}/data/server.json"
    jp_webhooks_path = f"{backup_dir}/v2/jp_webhooks.json"
    webhook_conf = f"{backup_dir}/v2/webhook.conf"
    new_webhooks_path = f"{backup_dir}/data/webhooks.json"
    jawa_address = ""
except IndexError:
    print("Backup directory not specified in program arguments.")
    exit(1)

# Create data dir in backup dir if necessary
if not os.path.isdir(f"{backup_dir}/data"):
    os.mkdir(f"{backup_dir}/data")

# Check for server.json
if os.path.isfile(old_server_json_path):
    with open(old_server_json_path) as fin:
        server_json = json.load(fin)
    for each_entry in server_json:
        new_server_json = each_entry
        jawa_address = each_entry.get("jawa_address")
        jps_url = each_entry.get("jps_url")
        new_server_json["alternate_jps"] = ""
    with open(new_server_json_path, "w") as fout:
        json.dump(new_server_json, fout, indent=4)

new_webhooks_json = []

# Checking for Jamf Pro webhooks
if os.path.isfile(jp_webhooks_path):
    with open(jp_webhooks_path) as fin:
        jp_webhooks_json = json.load(fin)
    for each_entry in jp_webhooks_json:
        new_entry = {
            "url": each_entry["url"],
            "jawa_admin": each_entry["username"],
            "name": each_entry["name"],
            "webhook_username": "null",
            "webhook_password": "null",
            "event": each_entry["event"],
            "script": each_entry["script"],
            "description": each_entry["description"],
            "tag": "jamfpro",
            "jamf_id": "",
        }
        new_webhooks_json.append(new_entry)

names = [each_entry["name"] for each_entry in new_webhooks_json]

# Checking for all other webhooks
if os.path.isfile(webhook_conf):
    with open(webhook_conf) as fin:
        webhooks_json = json.load(fin)

    for each_entry in webhooks_json:
        # Checking for unique entries
        if each_entry["id"] not in names:
            new_entry = {
                "url": jps_url,
                "jawa_admin": "Guy Incognito",
                "name": each_entry["id"],
                "webhook_username": "null",
                "webhook_password": "null",
                "script": each_entry["execute-command"],
                "description": "",
                "tag": "custom",
            }
            new_webhooks_json.append(new_entry)

# Writing new webhook file
with open(new_webhooks_path, "w+") as fout:
    json.dump(new_webhooks_json, fout, indent=4)
