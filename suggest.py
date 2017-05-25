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
import argparse

PUBLIC_URL = 'https://poloniex.com/public?command=%s'
BASE = {'BTC', 'ETH', 'XMR', 'USDT'}


def translate_trade(trade):
    return {'date': datetime.strptime(trade['date'], '%Y-%m-%d %H:%M:%S'),
            'tradeID': trade['tradeID'],
            'globalTradeID': trade['globalTradeID'],
            'total': float(trade['total']),
            'amount': float(trade['amount']),
            'rate': float(trade['rate']),
            'type': trade['type']}

def translate_ticker(val):
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
        ret = urlopen(Request(
            'https://poloniex.com/tradingApi',
            data=post_data,
            headers={'Sign': sign, 'Key': self._key})).read()
        return json.loads(ret.decode())

    def _run_public_command(self, command: str, req=None) -> str:
        req = {**(req if req else {}), **{'command': command}}
        post_data = '&'.join(['%s=%s' % (k, v) for k, v in req.items()])
        url = 'https://poloniex.com/public?'
        ret = urlopen(url + post_data).read()
        return json.loads(ret.decode())

    def get_trade_history(self, currency, coin, duration) -> dict:
        #https://poloniex.com/public?command=returnTradeHistory&currencyPair=BTC_NXT&start=1410158341&end=1410499372
        if currency == coin:
            return []
        return [translate_trade(t)
                for t in self._run_public_command(
                    'returnTradeHistory',
                    {'currencyPair': currency + '_' + coin,
                     'start': '%d' % (time.time() - duration),
                     'end': '9999999999',
                     })]

    def get_ticker(self) -> dict:
        return {c: translate_ticker(v)
                for c, v in self._run_public_command('returnTicker').items()}

    def get_balances(self) -> dict:
        return {c: float(v)
                for c, v in self._run_private_command('returnBalances').items()
                if float(v) > 0.0}


def get_price(ticker, currency, coin):
    return 1.0 if currency == coin else ticker['%s_%s' % (currency, coin)]['last']


def get_EUR():
    def get_bla():
        return json.loads(urlopen('http://api.fixer.io/latest').read().decode())
    return 1.0 / float(get_bla()['rates']['USD'])

def get_detailed_balances(api):

    print('get balances..')
    b = api.get_balances()
    print('get ticker..')
    t = api.get_ticker()
    print('get rates..')
    eur_price = get_EUR()
    print('get bitcoin price..')
    xbt_price = get_price(t, 'USDT', 'BTC')

    print('BTC price is USD %.2f / EUR %.2f' % (xbt_price, xbt_price * eur_price))

    hours = 2

    cash_usd = 0.0
    for c, v in sorted(b.items()):
        price = get_price(t, 'BTC', c)
        tot_usd = price * v * xbt_price
        cash_usd += tot_usd
        th = trade_history_digest(
            api.get_trade_history('BTC', c, 60 * 60 * hours))
        print('%r: a=%.5f, p=%.5f(last=%.5f), v=~EUR %6.2f, t=%+6.2f%% (%dh)' % (
            c, v, th['rate'], price, tot_usd * eur_price, th['trend'], hours))

    print('USD %.2f / EUR %.2f' % (cash_usd, cash_usd * eur_price))


def trade_history_digest(history, calculate_trend=True):
    if not history:
        return {'rate': 1.0,
                'amount': 0.0,
                'total': 0.0,
                'duration': 0,
                'trend': 0.0}
    #pprint(history)
    total = 0.0
    amount = 0.0
    for t in history:
        total += t['total']
        amount += t['amount']
    trend = ((trade_history_digest(history[:len(history) // 2], calculate_trend=False)['rate'] /
              trade_history_digest(history[len(history) // 2:], calculate_trend=False)['rate'] - 1.0 )
             if calculate_trend else 1.0)
    #print(history[0]['date'], "|", history[-1]['date'], "|", len(history), "|", total / amount)
    return {'rate': total / amount,
            'amount': amount,
            'total': total,
            'duration': int((history[0]['date'] - history[-1]['date']).total_seconds()),
            'trend': trend * 100,
            }


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='ticker')

    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument('cmd')
    return parser.parse_args()


def main():
    args = get_args()
    api = Api(**literal_eval(open('k').read()))

    if args.cmd == 'bal':
        get_detailed_balances(api)
    elif args.cmd == 'bla':
        t = api.get_ticker()
        for c, v in sorted(t.items(), key=lambda x: x[1]['percentChange'], reverse=True)[:5]:
            print(c, v['percentChange'])
    elif args.cmd == 'best':
        print('get balances..')
        for c, v in api.get_balances().items():
            print(c, v)
            print(trade_history_digest(api.get_trade_history('BTC', c, 60 * 60 * 2)))
    else:
        pass


#    pprint(t)
#    pprint(t.keys())
#    pprint(len(t))
#    for k in t:
#        h = get_trade_history(api, k)

    #pprint(get_trade_history(api, 'USDT_BTC'))
    # pprint(t)
    #pprint()
    #pprint(get_USDT_value(t, 'XMR'))
    #pprint(get_USDT_value(t, 'BTC'))


if __name__ == '__main__':
    main()

