#!/usr/bin/env python3

import sys
import os
import argparse
import time
import ujson as json
import logging as log
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import trader


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='history_server')

    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument("-c", "--allow-cached", action='store_true')
    return parser.parse_args()

def main():
    args = get_args()
    market = 'BTC_ETH'
    th = trader.TradeHistory(market)
    th.load('server')
    if th.get_duration() < 10*3600:
        print('fetch..')
        th.fetch_next(-1)
        #th.save()
    # data = th.data() #[-1000:]
    # [print(d) for d in data]
    bdata = th.rate_buckets(5 * 60)
    [print(d) for d in bdata]
    print('#%d/%.2fh => %d buckets' % (
        th.count(), th.get_duration() / 3600, len(bdata)))
    with open('processed_' + market + '.json', 'w') as f:
        json.dump(bdata, f)

if __name__ == '__main__':
    main()

