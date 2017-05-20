#!/usr/bin/env python3

import urllib
import json
from urllib.request import urlopen

URL = 'https://poloniex.com/public?command=returnTicker'

def main():

    with urlopen(URL) as conn:
        data = json.loads(conn.read().decode())

    for d, detail in data.items():
        c1, c2 = d.split('_')
        print(c1, c2, detail['highestBid'])

    print(len(data))

if __name__ == '__main__':
    main()
