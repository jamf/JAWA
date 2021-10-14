import json
import os
import sys

try:
    backup_dir = sys.argv[1]
    old_server_json_path = f'{backup_dir}/v2/server.json'
    new_server_json_path = f'{backup_dir}/data/server.json'
    jp_webhooks_path = f'{backup_dir}/v2/jp_webhooks.json'
    webhook_conf = f'{backup_dir}/v2/webhook.conf'
    new_webhooks_path = f'{backup_dir}/data/webhooks.json'
    jawa_address = ""
except IndexError as err:
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
        jawa_address = each_entry.get('jawa_address')
        jps_url = each_entry.get('jps_url')
    with open(new_server_json_path, 'w') as fout:
        json.dump(new_server_json, fout, indent=4)

new_webhooks_json = []

# Checking for Jamf Pro webhooks
if os.path.isfile(jp_webhooks_path):
    with open(jp_webhooks_path) as fin:
        jp_webhooks_json = json.load(fin)
    for each_entry in jp_webhooks_json:
        new_entry = {'url': each_entry['url'], 'jawa_admin': each_entry['username'], 'name': each_entry['name'],
                     'webhook_username': 'null', 'webhook_password': 'null', 'event': each_entry['event'],
                     'script': each_entry['script'], 'description': each_entry['description'], 'tag': "jamfpro",
                     'jamf_id': ""}
        new_webhooks_json.append(new_entry)

names = [each_entry['name'] for each_entry in new_webhooks_json]

# Checking for all other webhooks
if os.path.isfile(webhook_conf):
    with open(webhook_conf) as fin:
        webhooks_json = json.load(fin)

    for each_entry in webhooks_json:
        # Checking for unique entries
        if each_entry['id'] not in names:
            new_entry = {'url': jps_url, 'jawa_admin': 'Guy Incognito', 'name': each_entry['id'],
                         'webhook_username': 'null', 'webhook_password': 'null',
                         'script': each_entry['execute-command'],
                         'description': "", 'tag': "custom"}
            new_webhooks_json.append(new_entry)

# Writing new webhook file
with open(new_webhooks_path, 'w+') as fout:
    json.dump(new_webhooks_json, fout, indent=4)
