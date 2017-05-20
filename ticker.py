#!/usr/bin/env python3

import urllib
import json
from datetime import datetime
from urllib.request import urlopen

URL = 'https://poloniex.com/public?command=returnTicker'

def get_ticker() -> dict:
    json_data = urlopen(URL).read().decode()
    open('{:%Y.%m.%d-%H.%M.%S}.json'.format(datetime.now()), 'w').write(json_data)
    return json.loads(json_data)

def main():

    data = {}
    targets = set()

    for d, detail in get_ticker().items():
        c1, c2 = d.split('_')
        targets.add(c2)
        print(c1, c2, detail['highestBid'])
        if c1 not in data:
            data[c1] = {}
        data[c1][c2] = detail

    print(data.keys())

    if not set(data.keys()) == {'BTC', 'ETH', 'XMR', 'USDT'}:
        print(data.keys())

    for cur1, exch in data.items():
        for cur2 in data:
            print(cur1, cur2, cur2 in exch)
            

    print(targets)
    print(len(targets))

if __name__ == '__main__':
    main()
