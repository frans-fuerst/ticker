#!/usr/bin/env python3

import ast
import logging as log
import argparse
import trader
import time
from trader_ui import show_gui


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='ticker')
    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument("-c", "--allow-cached", action='store_true')
    parser.add_argument('cmd')
    parser.add_argument('arg1', nargs='?')
    parser.add_argument('arg2', nargs='?')
    parser.add_argument('arg3', nargs='?')
    parser.add_argument('arg4', nargs='?')
    return parser.parse_args()


def main():
    args = get_args()
    log.basicConfig(level=log.DEBUG if args.verbose else log.INFO)
    trader.ALLOW_CACHED_VALUES = 'ALLOW' if args.allow_cached else 'NEVER'
    try:
        api = trader.Api(**ast.literal_eval(open('k').read()))
    except FileNotFoundError:
        log.warning('did not find key file - only public access is possible')
        api = None

    if args.cmd == 'bal':
        trader.get_detailed_balances(api)
    elif args.cmd == 'bla':
        t = api.get_ticker()
        for c, v in sorted(t.items(), key=lambda x: x[1]['percentChange'], reverse=True)[:5]:
            print(c, v['percentChange'])
    elif args.cmd == 'best':
        print('get balances..')
        for c, v in api.get_balances().items():
            print(c, v)
            print(trader.trade_history_digest(
                api.get_trade_history('BTC', c, 60 * 60 * 2)))
    elif args.cmd == 'trade':
        api.place_order(
            sell=(float(args.arg1), args.arg2),
            buy=args.arg3,
            rate=None,
            fire=args.arg4=='fire')
        print('your orders:', api.get_open_orders())
    elif args.cmd == 'gui':
        show_gui()
    else:
        h = trader.TradeHistory('BTC_XMR', step_size_sec=60)
        for i in range(2):
            h.fetch_next()
            print(time.time() - h.last_time())

            print(h)
            time.sleep(20)
        #api.place_order(sell=(0.001, 'BTC'), buy='FLO', fire=True)
        #api.place_order(sell=(3, 'XMR'), buy='BTC')
        #api.place_order(sell=(0.004, 'BTC'), buy='XMR')
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

