#!/usr/bin/env python3

import logging as log
import time
import argparse
import trader

def serve(interval):

    while True:
        try:
            for p, secondaries in trader.Api.get_markets().items():
                for s in secondaries:
                    print('%s_%s' % (p, s))
                # trader.Api.get_trade_history(coin, duration)
        except trader.ServerError as exc:
            log.warning('Could not communicate with Trading server (%r)', exc)
        time.sleep(interval)


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='ticker')

    parser.add_argument("-v", "--verbose", action='store_true')
    return parser.parse_args()


def main():
    args = get_args()
    log.basicConfig(level=log.DEBUG if args.verbose else log.INFO)
    serve(interval=5)

if __name__ == '__main__':
    main()

