#!/usr/bin/env python3

import sys
import os
import argparse
import time
import logging as log

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import mftl
import mftl.qwtgraph


def foo():

    now = time.time()

    th = mftl.TradeHistory('BTC_ETH', step_size_sec=6*3600)
    th.load()

    if th.get_duration() < 10 * 3600:
        th.fetch_next()
        th.save()

        # print(th.count(), th.get_duration()/3600)

    data = th.data() #[-10000:]

    #        [print(d) for d in data]

    print((data[-1]['time']-data[0]['time']) / 3600)

    #totals = [e['total'] for e in data]
    #amounts = [e['amount'] for e in data]
    rates = [e['total'] / e['amount'] for e in data]
    times = [e['time'] - now for e in data]
    #full = [(e['time'] - now, e['total'], e['amount'], e['total'] / e['amount']) for e in data]

    #[print('%.2f, %11.8f, %11.8f, %9.9f' % d) for d in full]

    #rates_vema_slow = mftl.vema(totals, amounts, 0.001)
    #rates_vema_fast = mftl.vema(totals, amounts, 0.004)

    candlestick_data = th.rate_buckets()
    times2 = [e['time'] - now for e in candlestick_data]
    rates_sell = [e['total_sell'] / e['amount_sell'] for e in candlestick_data]
    rates_buy = [e['total_buy'] / e['amount_buy'] for e in candlestick_data]
    #amounts_sell = [e['amount_sell'] for e in candlestick_data]
    #totals_sell = [e['total_sell'] for e in candlestick_data]

    #rates_vema_fast = mftl.vema(totals_sell, amounts_sell, 0.1)
    #rates_vema_slow = mftl.vema(totals_sell, amounts_sell, 0.1)

    w = mftl.qwtgraph.GraphUI()
    w.set_data(times, rates)

    w.set_data(times, rates, 'gray')

    w.set_data(times2, rates_sell, 'fat_blue')
    w.set_data(times2, rates_buy, 'fat_red')
    #w.set_data(times2, rates_vema_fast, Qt.QPen(Qt.Qt.red, 2, Qt.Qt.SolidLine))
    #w.set_data(times2, rates_vema_slow, Qt.QPen(Qt.Qt.blue, 2, Qt.Qt.SolidLine))

    w.show()


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='history_server')
    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument("-c", "--allow-cached", action='store_true')
    return parser.parse_args()


def main():
    args = get_args()
    log.basicConfig(level=log.INFO)
    mftl.util.ALLOW_CACHED_VALUES = 'ALLOW' if args.allow_cached else 'NEVER'

    with mftl.qwtgraph.qtapp() as app:
        foo()
        app.run()


if __name__ == '__main__':
    main()

