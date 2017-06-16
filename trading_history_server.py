#!/usr/bin/env python3

import logging as log
import time
import argparse
import http.server
import socketserver

import trader


class HistoryServer(http.server.BaseHTTPRequestHandler):
    def __init__(self, request, client_address, server):
        http.server.BaseHTTPRequestHandler.__init__(
            self, request, client_address, server)

    def do_GET(self):
        print(self.path)
        if True:
            self.send_response(200)
            self.send_header('Content type', 'application/octet-stream')
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(_archive.read())
        else:
            self.send_error(404)

    def do_POST(self):
        print(self.path)
        if True:
            self.send_response(201)
        else:
            self.send_error(e.code, e.description)

        self.close_connection = True
        self.end_headers()


def start_server(port):
    socketserver.TCPServer.allow_reuse_address = True
    http_server = socketserver.TCPServer(('', port), HistoryServer)
    http_server.serve_forever()

def init():
    result = {}
    for m, secondaries in trader.Api.get_ticker().items():
        if not m.startswith('BTC_'): continue
        coin = m.split('_')[1]
        if trader.get_full_name(coin).startswith('unknown'): continue
        if coin not in {'XRP', 'ETH', 'ETC', 'XMR', 'XRP', 'DOGE'}: continue
        print(m)
        result[m] = trader.TradeHistory(
            m,
            step_size_sec=4*3600,
            history_max_duration=10*365*24*3600,
            update_threshold=5*3600)
        result[m].load('server')
    return result

def serve(interval):

    # start_server(8080)
    markets = init()
    print('--')
    while True:
        t1 = time.time()
        print('fetch..')
        for m, th in markets.items():
            print(m)
            count_before = th.count()
            tu = time.time()
            for _ in range(3):
                try:
                    th.fetch_next(-1, only_old=True)
                    break
                except trader.ServerError as exc:
                    print('(WW) %r' % exc)
            print('#%d(+%d)/%.2fh took %.1fsec' % (
                th.count(), th.count() - count_before,
                th.get_duration() / 3600, time.time() - tu))
            th.save('server')
            time.sleep(0.2)
        t2 = time.time()
        print('update took %.1fs' % (t2 - t1))



def get_args() -> dict:
    parser = argparse.ArgumentParser(description='history_server')

    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument("-c", "--allow-cached", action='store_true')
    return parser.parse_args()


def main():
    args = get_args()
    log.basicConfig(level=log.DEBUG if args.verbose else log.INFO)
    trader.ALLOW_CACHED_VALUES = 'ALLOW' if args.allow_cached else 'NEVER'
    serve(interval=5)


if __name__ == '__main__':
    main()

