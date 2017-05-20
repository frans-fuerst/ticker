#!/usr/bin/env python3

import urllib
import json
import sys
from pprint import pprint
from datetime import datetime
from urllib.request import urlopen

URL = 'https://poloniex.com/public?command=returnTicker'


def get_ticker() -> str:
    json_data = urlopen(URL).read().decode()
    open('{:%Y.%m.%d-%H.%M.%S}.json'.format(datetime.now()), 'w').write(json_data)
    return json_data


def main():

    data = {}
    targets = set()
    in_data = json.loads(open(sys.argv[1]).read() if len(sys.argv) > 1 else 
                         get_ticker())

    for d, detail in in_data.items():
        c1, c2 = d.split('_')
#        print(c1, c2)
        targets.add(c2)
#        print(c1, c2, detail.keys())
        if c1 not in data:
            data[c1] = {}
        data[c1][c2] = detail

    pprint(in_data['BTC_XEM'])

    print(data.keys())
    for c1, detail in data.items():
        print(c1, list(detail.keys()))

    if not set(data.keys()) == {'BTC', 'ETH', 'XMR', 'USDT'}:
        print(data.keys())

    print(targets)
    print(len(targets))

    print(len(data['BTC']))
    for e, detail in data['BTC'].items():
        print(e, detail['last'])

if __name__ == '__main__':
    main()

