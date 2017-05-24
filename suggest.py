#!/usr/bin/env python3

import json
from urllib.request import urlopen, Request
import urllib
import urllib3
from datetime import datetime
from pprint import pprint
from ast import literal_eval
import hmac
import hashlib
import time

PUBLIC_URL = 'https://poloniex.com/public?command=%s'
BASE = {'BTC', 'ETH', 'XMR', 'USDT'}

class Api:
    def __init__(self, key, secret):
        self._key = key.encode()
        self._secret = secret.encode()

    def run_private_command(self, command, req=None):
        req = req if req else {}
        req.update({
            'command': command,
            'nonce': int(time.time() * 1000)})
        post_data = urllib.parse.urlencode(req).encode()
        sign = hmac.new(
            self._secret,
            msg=post_data,
            digestmod=hashlib.sha512).hexdigest()
        ret = urlopen(Request(
            'https://poloniex.com/tradingApi',
            data=post_data,
            headers={'Sign': sign, 'Key': self._key})).read()
        return json.loads(ret.decode())


def run_command(command: str) -> str:
    json_data = urlopen(PUBLIC_URL % command).read().decode()
    open('{:%Y.%m.%d-%H.%M.%S}.json'.format(datetime.now()), 'w').write(json_data)
    return json_data


def get_ticker() -> dict:
    return json.loads(run_command('returnTicker'))

def get_balances(api) -> dict:
    return {c: float(v) for c, v in api.run_private_command('returnBalances').items() if float(v) > 0.0}

def main():
    api = Api(**literal_eval(open('k').read()))
    pprint(get_balances(api))
    # pprint(get_ticker())


if __name__ == '__main__':
    main()

