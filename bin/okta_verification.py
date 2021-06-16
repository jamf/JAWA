#!/usr/bin/python

from flask import request
import json
import sys


def verify_new_webhook(challenge):
    # challenge = sys.argv[2]
    # verification = request.headers.get('x-okta-verification-challenge')
    json_text = {f"verification": f"{challenge}"}
    print(json.dumps(json_text))
    return json_text


def main():
    pass


if __name__ == '__main__':
    main()
