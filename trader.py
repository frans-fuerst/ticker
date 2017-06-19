#!/usr/bin/env python3

from mftl.px import private_request, public_request

import os
#import http
#import urllib
#from urllib.request import urlopen, Request
#from datetime import datetime
#from pprint import pprint
#import hmac
#import hashlib
#import socket
import logging as log
#import time
#import threading

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




def get_price(ticker, currency, coin):
    return 1.0 if currency == coin else ticker['%s_%s' % (currency, coin)]['last']


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

