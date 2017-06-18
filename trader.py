#!/usr/bin/env python3

from mftl.px import private_request, public_request

import os
try:
    import ujson as json
except ImportError:
    import json
import http
import urllib
from urllib.request import urlopen, Request
from datetime import datetime
from pprint import pprint
import hmac
import hashlib
import socket
import logging as log
import time
import threading

MOST_RECENTLY = 9999999999


def merge_time_list(list1, list2):
    return list2


def expand_bucket(bucket):
    amount = bucket['amount_buy'] + bucket['amount_sell']
    total = bucket['total_buy'] + bucket['total_sell']
    return {**bucket, **{
        'amount': amount,
        'total': total,
        'rate': total / amount,
    }}

def get_plot_data(data, ema_factor):
    totals = [e['total'] for e in data]
    amounts = [e['amount'] for e in data]
    times = [time.mktime(e['date'].timetuple()) - time.time() for e in data]

    rates_vema = vema(totals, amounts, ema_factor)

    return times, rates_vema


def get_unique_name(data: dict) -> str:
    ''' turn dict into unambiguous string '''
    return ('.'.join('%s=%s' % (k, 'xxx' if k in {'start', 'nonce'} else v)
                      for k, v in sorted(data.items()))
            .replace(',', '_')
            .replace('/', '_')
            .translate(dict.fromkeys(map(ord, u"\"'[]{}() "))))




class Api:
    def __init__(self, key, secret):
        self._key = key.encode()
        self._secret = secret.encode()
        self._coins = None
        self._markets = None

    @staticmethod
    def _get_trade_history(currency_pair, start=None, stop=None) -> dict:
        req = {'currencyPair': currency_pair}
        if start is not None:
            if start == 0:
                start = time.time() - (360*24*3600)
            req.update({'start': start if stop is not None else time.time() - start,
                        'end': stop if stop is not None else MOST_RECENTLY})
        translated = (translate_dataset(t) for t in Api._run_public_command(
            'returnTradeHistory', req))
        cleaned = (e for e in translated
                   if e['amount'] > 0.000001 and e['total'] > 0.000001)
        return list(reversed(list(cleaned)))

    @staticmethod
    def get_trade_history(primary, coin, start, stop=None) -> dict:
        if primary == coin:
            return []
        return Api._get_trade_history(primary + '_' + coin, start, stop)

    @staticmethod
    def get_current_rate(market):
        total, amount, minr, maxr = sum_trades(Api._get_trade_history(market))
        return total / amount, minr, maxr

    @staticmethod
    def get_ticker() -> dict:
        return {c: translate_dataset(v)
                for c, v in Api._run_public_command('returnTicker').items()}

    def get_balances(self) -> dict:
        return {c: float(v)
                for c, v in self._run_private_command('returnBalances').items()
                if float(v) > 0.0}

    def get_complete_balances(self) -> dict:
        return {c: {k: float(a) for k, a in v.items()}
                for c, v in self._run_private_command(
                    'returnCompleteBalances').items()}

    def cancel_order(self, order_nr) -> dict:
        return self._run_private_command(
            'cancelOrder', {'orderNumber': order_nr})

    def get_open_orders(self) -> dict:
        return {c: [translate_dataset(o) for o in order_list]
                for c, order_list in self._run_private_command(
                    'returnOpenOrders', {'currencyPair': 'all'}).items()
                if order_list}

    def get_order_history(self) -> dict:
        return {c: [translate_dataset(o) for o in order_list]
                for c, order_list in self._run_private_command(
                    'returnTradeHistory', {'currencyPair': 'all',
                                           'start': 0,
                                           'end': MOST_RECENTLY}).items()}

    @staticmethod
    def extract_coin_data(ticker):
        coins = {}
        for m in ticker:
            c1, c2 = m.split('_')
            if not c1 in coins: coins[c1] = set()
            coins[c1].add(c2)
        return coins

    def get_coins(self, refetch=False):
        ''' returns
        '''
        if refetch or not self._coins:
            ticker = self.get_ticker()
            self._coins = self.extract_coin_data(ticker)
            self._markets = ticker.keys()
        return self._coins

    def get_markets(self, refetch=False):
        if refetch or not self._markets:
            ticker = self.get_ticker()
            self._coins = self.extract_coin_data(ticker)
            self._markets = ticker.keys()
        return self._markets

    def check_order(self, *,
                    sell: tuple, buy: str,
                    suggestion_factor: float,
                    balances: dict) -> float:
        amount, what_to_sell = sell
        log.info('try to sell %f %r for %r', amount, what_to_sell, buy)# todo: correct

        if not what_to_sell in balances:
            raise ValueError(
                'You do not have %r to sell' % what_to_sell)
        log.info('> you have %f %r', balances[what_to_sell], what_to_sell)
        if balances[what_to_sell] < amount:
            raise ValueError(
                'You do not have enough %r to sell (just %f)' % (
                    what_to_sell, balances[what_to_sell]))

        if (what_to_sell in self.get_coins() and
                buy in self.get_coins()[what_to_sell]):
            market = what_to_sell + '_' + buy
            action = 'buy'
        elif (buy in self.get_coins() and
                  what_to_sell in self.get_coins()[buy]):
            market = buy + '_' + what_to_sell
            action = 'sell'
        else:
            raise ValueError(
                'No market available for %r -> %r' % (
                    what_to_sell, buy))

        # [todo]: make sure this is correct!!!
        current_rate, minr, maxr = self.get_current_rate(market)

        target_rate = (
            current_rate * suggestion_factor if action == 'buy' else
            current_rate / suggestion_factor)

        log.info('> current rate is %f(%f..%f), target is %f',
                 current_rate, minr, maxr, target_rate)

        return {'market': market,
                'action': action,
                'rate': target_rate,
                'amount': (amount if action == 'sell' else
                           amount / target_rate)}

    def place_order(self, *,
                    market: str,
                    action: str,
                    rate: float,
                    amount: float) -> dict:
        assert action in {'buy', 'sell'}
        log.info('place order: %r %r %f %f', market, action, rate, amount)
        return self._run_private_command(
            action,
            {'currencyPair': market,
             'rate': rate,
             'amount': amount})


def get_price(ticker, currency, coin):
    return 1.0 if currency == coin else ticker['%s_%s' % (currency, coin)]['last']


def get_EUR():
    def get_bla():
        return json.loads(_fetch_http(
            'https://api.fixer.io/latest', {'url':'api.fixer.io/latest'}))
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
    pprint(api.get_order_history())


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

