#!/usr/bin/env python3

import os
import trader
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


def trade(th, ema_slow, ema_fast):
    amount_BTC = 100.
    amount_XMR = 0.

    _, ma_slow = th.get_plot_data(ema_factor=ema_slow, cut=0)
    _, ma_fast = th.get_plot_data(ema_factor=ema_fast, cut=0)
    trades = 0
    last_BTC = 0
    last_XMR = 0
    for i, d in enumerate(th.data()):
        if i == 0: continue
        action = ('sell' if ma_fast[i] < ma_slow[i] and ma_fast[i - 1] > ma_slow[i - 1] else
                  'buy' if ma_fast[i] > ma_slow[i] and ma_fast[i - 1] < ma_slow[i - 1] else
                  'none')
        if action == 'none': continue
        if action == 'buy':
            if amount_BTC == 0.: continue
            new_c2 = amount_BTC / d['rate'] * fee
            amount_XMR = new_c2
            last_BTC, amount_BTC = amount_BTC, 0.
        elif action == 'sell':
            if amount_XMR == 0.: continue
            new_c1 = amount_XMR * d['rate'] * fee
            amount_BTC = new_c1
            last_XMR, amount_XMR = amount_XMR, 0.
        trades += 1
#        print(i, d['time'], amount_BTC, amount_XMR, action, d['rate'])
    return last_BTC, last_XMR, trades

def try_market(m):
    print(m)
    #btc_xmr_th = trader.TradeHistory('BTC_XMR')
    #btc_xmr_th = trader.TradeHistory('BTC_ARDR')  # 0.0008 / 0.004
    btc_xmr_th = trader.TradeHistory(m)  # 0.0008 / 0.004
    btc_xmr_th.load()
    #fee = 1

    #while btc_xmr_th.get_duration() < 10 * 3600:
    #    print('fetch..')
    #    btc_xmr_th.fetch_next()

    print('#: %d / %d.2h'% (btc_xmr_th.count(), btc_xmr_th.get_duration() / 3600))

    bmax = 0
    stepsi = 25
    stepsj = 25
    for i in range(stepsi):
        for j in range(stepsj):
            ema_fast = 0.01/stepsi * i
            ema_slow = 0.01/stepsj * j
            b, x, t = trade(btc_xmr_th, ema_slow, ema_fast)
            if bmax < b:
                bmax = b
                best = (i, j, b, b, x, t, ema_slow, ema_fast, ema_fast > ema_slow)
                print('i%d/j%d, %.3f%% C1:%.4f C2:%.4f #%d slow=%.6f fast=%.6f %r' % best)

#for f in os.listdir():
    #if not (f.startswith('trade_history') and f.endswith('.json')):
        #continue
    #m = f.split('.')[0].split('-')[1]
    #try_market(m)

try_market('BTC_XRP')
