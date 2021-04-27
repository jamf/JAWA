#!/usr/bin/python

import json
import sys

challenge = sys.argv[2]

json_text = {"verification": "{}".format(challenge)}

print(json.dumps(json_text))
