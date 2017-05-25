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

    def _run_private_command(self, command, req=None):
        req = req if req else {}
        req.update({
            'command': command,
            'nonce': int(time.time() * 1000)})
        post_data = urllib.parse.urlencode(req).encode()
        sign = hmac.new(
            self._secret,
            msg=post_data,
            digestmod=hashlib.sha512).hexdigest()
        r = Request(
            'https://poloniex.com/tradingApi',
            data=post_data,
            headers={'Sign': sign, 'Key': self._key})
        ret = urlopen(r).read()
        return json.loads(ret.decode())

    def _run_public_command(self, command: str, req=None) -> str:
        req = {**(req if req else {}), **{'command': command}}
        post_data = '&'.join(['%s=%s' % (k, v) for k, v in req.items()])
        url = 'https://poloniex.com/public?'
        ret = urlopen(url + post_data).read()
        return json.loads(ret.decode())

    def get_trade_history(self, currency_pair) -> dict:
        return self._run_public_command(
            'returnTradeHistory', {'currencyPair': currency_pair})

    def get_ticker(self) -> dict:
        def translate(val):
            return {'baseVolume': float(val['baseVolume']),
                    'high24hr': float(val['high24hr']),
                    'highestBid': float(val['highestBid']),
                    'id': val['id'],
                    'isFrozen': val['id'] != '0',
                    'last': float(val['last']),
                    'low24hr': float(val['low24hr']),
                    'lowestAsk': float(val['lowestAsk']),
                    'percentChange': float(val['percentChange']),
                    'quoteVolume': float(val['quoteVolume'])}
        return {c: translate(v)
                for c, v in self._run_public_command('returnTicker').items()}

    def get_balances(self) -> dict:
        return {c: float(v)
                for c, v in self._run_private_command('returnBalances').items()
                if float(v) > 0.0}


def get_price(ticker, currency, coin):
    return 1.0 if currency == coin else ticker['%s_%s' % (currency, coin)]['last']


def main():
    api = Api(**literal_eval(open('k').read()))

    b = api.get_balances()
    t = api.get_ticker()
    xbt_price = get_price(t, 'USDT', 'BTC')
    cash = 0.0
    for c, v in sorted(b.items()):
        p = get_price(t, 'BTC', c)
        tot = p * v * xbt_price
        cash += tot
        print('%r: %.5f %.5f $%.2f' % (c, v, p, tot))
    print('$%.2f' % cash)

    #pprint(get_trade_history(api, 'USDT_BTC'))
    # pprint(t)
    #pprint()
    #pprint(get_USDT_value(t, 'XMR'))
    #pprint(get_USDT_value(t, 'BTC'))


if __name__ == '__main__':
    main()

