#!/usr/bin/env python3

import sys
import os
import argparse
import time
import logging as log

import trader


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='history_server')

    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument("-c", "--allow-cached", action='store_true')
    return parser.parse_args()


def main():
    args = get_args()
    th = trader.TradeHistory('BTC_ETH')
    th.load('server')
    data = th.data() #[-1000:]
    #[print(d) for d in data]
    print(th.count(), th.get_duration()/3600)

if __name__ == '__main__':
    main()

