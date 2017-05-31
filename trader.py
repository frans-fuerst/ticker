#!/usr/bin/env python3

__all__ = ['translate_trade']

import json
import urllib
from urllib.request import urlopen, Request
from datetime import datetime
from pprint import pprint
import hmac
import hashlib
import logging as log
import time

ALLOW_CACHED_VALUES = 'ALLOW'  # 'NEVER', 'FORCE'


class ServerError(RuntimeError):
    pass

def get_rates(data):
    return tuple(x['total'] / x['amount'] for x in data)


def clean(data):
    return data

def get_unique_name(data):
    x = repr(list('%s_%s' % (k, 'xxx' if k=='start' else v) for k, v in sorted(data.items())))
    return (x
            .replace(':', '=')
            .replace(',', '_')
            .translate(dict.fromkeys(map(ord, u"\"'[]{}() "))))


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
        self._markets = self.get_markets()

    @staticmethod
    def _fetch(request, request_data):
        assert ALLOW_CACHED_VALUES in {'NEVER', 'ALLOW', 'FORCE'}
        filename = get_unique_name(request_data) + '.cache'
        if ALLOW_CACHED_VALUES in {'NEVER', 'ALLOW'}:
            try:
                result = urlopen(request).read()
                with open(filename, 'wb') as file:
                    file.write(result)
                return result
            except urllib.error.URLError as exc:
                if ALLOW_CACHED_VALUES == 'NEVER':
                    raise ServerError(str(exc)) from exc
        try:
            with open(filename, 'rb') as file:
                log.warning('use chached values for %r', request)
                return file.read()
        except FileNotFoundError as exc:
            raise ServerError(str(exc)) from exc

    def _run_private_command(self, command, req=None):
        request_data = {**(req if req else {}),
                        **{'command': command,
                           'nonce': int(time.time() * 1000)}}
        post_data = urllib.parse.urlencode(request_data).encode()
        sign = hmac.new(
            self._secret,
            msg=post_data,
            digestmod=hashlib.sha512).hexdigest()
        request = Request(
            'https://poloniex.com/tradingApi',
            data=post_data,
            headers={'Sign': sign, 'Key': self._key})
        result = json.loads(Api._fetch(request, request_data).decode())
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    @staticmethod
    def _run_public_command(command: str, req=None) -> str:
        request_data = {**(req if req else {}),
                        **{'command': command}}
        post_data = '&'.join(['%s=%s' % (k, v) for k, v in request_data.items()])
        request = 'https://poloniex.com/public?' + post_data
        result = json.loads(Api._fetch(request, request_data).decode())
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    @staticmethod
    def _get_trade_history(currency_pair, duration=None) -> dict:
        req = {'currencyPair': currency_pair}
        if duration:
            req.update({'start': '%d' % (time.time() - duration),
                        'end': '9999999999'})
        return [translate_trade(t)
                for t in Api._run_public_command(
                    'returnTradeHistory', req)]

    @staticmethod
    def get_trade_history(primary, coin, duration) -> dict:
        if primary == coin:
            return []
        return Api._get_trade_history(primary + '_' + coin, duration)

    @staticmethod
    def get_current_rate(market):
        total, amount, minr, maxr = sum_trades(Api._get_trade_history(market))
        return total / amount, minr, maxr

    @staticmethod
    def get_ticker() -> dict:
        return {c: translate_ticker(v)
                for c, v in Api._run_public_command('returnTicker').items()}

    def get_balances(self) -> dict:
        return {c: float(v)
                for c, v in self._run_private_command('returnBalances').items()
                if float(v) > 0.0}

    def get_complete_balances(self) -> dict:
        return {c: {k: float(a) for k, a in v.items()}
                for c, v in self._run_private_command('returnCompleteBalances').items()}

    def get_open_orders(self) -> dict:
        return {c: o
                for c, o in self._run_private_command('returnOpenOrders', {'currencyPair': 'all'}).items()
                if o}

    @staticmethod
    def get_markets():
        markets = {}
        for m in Api.get_ticker():
            c1, c2 = m.split('_')
            if not c1 in markets: markets[c1] = set()
            markets[c1].add(c2)
        return markets

    def place_order(self, *, sell: tuple, buy: str, fire=False):
        amount, what_to_sell = sell
        print('try to sell %f %r for %r' % (amount, what_to_sell, buy))

        def check_balance():
            balances = self.get_balances()
            if not what_to_sell in balances:
                raise ValueError(
                    'You do not have %r to sell' % what_to_sell)
            print('> you have %f %r' % (balances[what_to_sell], what_to_sell))
            if balances[what_to_sell] < amount:
                raise ValueError(
                    'You do not have enough %r to sell (just %f)' % (
                        what_to_sell, balances[what_to_sell]))

        check_balance()
        if (what_to_sell in self._markets and
                buy in self._markets[what_to_sell]):
            market = what_to_sell + '_' + buy
            action = 'buy'
        elif (buy in self._markets and
                  what_to_sell in self._markets[buy]):
            market = buy + '_' + what_to_sell
            action = 'sell'
        else:
            raise ValueError(
                'No market available for %r -> %r' % (
                    what_to_sell, buy))
        current_rate, minr, maxr = self.get_current_rate(market)
        # [todo]: here we can raise/lower by about 0.5%
        target_rate = current_rate
        target_amount = amount if action == 'sell' else amount / target_rate

        print('> current rate is %f(%f-%f), target is %f' % (
            current_rate, minr, maxr, target_rate))
        print('> %r currencyPair=%s, rate=%f, amount=%f' % (
            action, market, target_rate, target_amount))
        if fire:
            print('> send trade command..')
            pprint(self._run_private_command(
                action,
                {'currencyPair': market,
                 'rate': target_rate,
                 'amount': target_amount}))


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
    pprint(api.get_open_orders())


def sum_trades(history: list) -> tuple:
    total = 0.0
    amount = 0.0
    min_rate = +99999999
    max_rate = -99999999
    for t in history:
        total += t['total']
        amount += t['amount']
        min_rate = min(min_rate, t['rate'])
        max_rate = max(max_rate, t['rate'])
    return total, amount, min_rate, max_rate


def trade_history_digest(history, calculate_trend=True):
    if not history:
        return {'rate': 1.0,
                'amount': 0.0,
                'total': 0.0,
                'duration': 0,
                'trend': 0.0}
    #pprint(history)
    trend = ((trade_history_digest(history[:len(history) // 2], calculate_trend=False)['rate'] /
              trade_history_digest(history[len(history) // 2:], calculate_trend=False)['rate'] - 1.0 )
             if calculate_trend else 1.0)
    #print(history[0]['date'], "|", history[-1]['date'], "|", len(history), "|", total / amount)
    total, amount, _, _ = sum_trades(history)
    return {'rate': total / amount,
            'amount': amount,
            'total': total,
            'duration': int((history[0]['date'] - history[-1]['date']).total_seconds()),
            'trend': trend * 100,
            }

