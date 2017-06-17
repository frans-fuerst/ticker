#!/usr/bin/env python3

import os, sys
import time
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import trader
import utils

fee = 0.9975

def random_trade(th):
    amount_BTC = 100.
    amount_XMR = 0.
    for i, d in enumerate(th.data()):
        if i % 100 == 0:
            action = 'buy' if i // 100 % 2 == 0 else 'sell'
            if action == 'buy':
                amount_XMR = amount_BTC / d['rate'] * fee
                amount_BTC = 0.
            elif action == 'sell':
                amount_BTC = amount_XMR * d['rate'] * fee
                amount_XMR = 0.
            print(i, action, amount_BTC, amount_XMR)


def trade(times, totals, amounts, rates, alpha_ema_slow, alpha_ema_fast):
    amount_C1 = 100.
    amount_C2 = 0.

    ma_slow = trader.vema(totals, amounts, alpha_ema_slow)
    ma_fast = trader.vema(totals, amounts, alpha_ema_fast)

    if True:
        w = utils.GraphUI()
        w.set_data(times, rates)
        w.set_data(times, ma_slow, 'fat_blue')
        w.set_data(times, ma_fast, 'fat_red')
        w.show()
    else:
        w = None

    trades = 0
    last_C1 = 0
    last_C2 = 0
    for i, d in enumerate(rates):
        if i == 0: continue
        # verkaufen, wenn fast MA
        action = ('buy' if ma_fast[i] >= ma_slow[i] and ma_fast[i - 1] < ma_slow[i - 1] else
                  'sell' if ma_fast[i] <= ma_slow[i] and ma_fast[i - 1] > ma_slow[i - 1] else
                  'none')
        if action == 'none': continue
        if action == 'buy':
            if amount_C1 == 0.: continue
            new_c2 = amount_C1 / d * fee
            amount_C2 = new_c2
            last_C1, amount_C1 = amount_C1, 0.
        elif action == 'sell':
            if amount_C2 == 0.: continue
            new_c1 = amount_C2 * d * fee
            amount_C1 = new_c1
            last_C2, amount_C2 = amount_C2, 0.
        if True and w:
            w.add_vmarker(times[i], 'red' if action == 'sell' else 'green')
            w.add_hmarker(d, 'red' if action == 'sell' else 'green')
        trades += 1
        print('%.4d %.7d %9.2f %11.2f %11.9f %s' % (
            i, times[i], amount_C1, amount_C2, d, action))
    return last_C1, last_C2, trades

def try_market(m):
    print(m)
    th = trader.TradeHistory(m)  # 0.0008 / 0.004
    th.load()

    if th.get_duration() < 10 * 3600:
        print('fetch..')
        for i in range(3):
            try:
                th.fetch_next(-1)
                break
            except trader.ServerError:
                pass
#        th.save()

    now = time.time()
    cdata = [trader.expand_bucket(b) for b in th.rate_buckets(60)] #[-500:]
    times = [(e['time'] - now) / 3600 for e in cdata]
    rates = [e['rate'] for e in cdata]
    amounts = [e['amount_sell'] for e in cdata]
    totals = [e['total_sell'] for e in cdata]

    print('#: %d / %.2fh buckets: %d'% (
        th.count(), th.get_duration() / 3600, len(times)))

    if False:

        bmax = 0
        stepsi = 50
        stepsj = 30
        for i in range(stepsi):
            for j in range(stepsj):
                ema_fast = 0.1 / stepsi * i
                ema_slow = ema_fast / stepsj * j
                b, x, t = trade(times, totals, amounts, rates, ema_slow, ema_fast)
                if bmax < b:
                    bmax = b
                    best = (i, j, b - 100., b, x, t, ema_slow, ema_fast, ema_fast > ema_slow)
        print('i%d/j%d, %.3f%% C1:%.4f C2:%.4f #%d slow=%.6f fast=%.6f %r' % best)
    else:
#        print(trade(times, totals, amounts, rates, 0.008000, 0.036000))
        #        print(trade(times, totals, amounts, rates, 0.001000, 0.036000))
        print(trade(times, totals, amounts, rates, 0.00100, 0.00200))

def main():
    with utils.qtapp(True) as app:
        if False:
            for f in os.listdir('..'):
                if not (f.startswith('trade_history') and f.endswith('.json')):
                    continue
                m = f.split('.')[0].split('-')[1]
                try_market(m)
        else:
            try_market('BTC_ARDR')
#            try_market('BTC_ETC')
        app.run()

if __name__ == '__main__':
    main()