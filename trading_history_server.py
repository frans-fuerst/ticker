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


def serve(interval):

    # start_server(8080)
    while True:
        try:
            for p, secondaries in trader.Api.get_markets().items():
                for s in secondaries:
                    print('%s_%s' % (p, s))
                    trader.Api.get_trade_history(p, s, 5*60*60)
            log.info('all coins fetched')
            break
        except trader.ServerError as exc:
            log.warning('Could not communicate with Trading server (%r)', exc)
        time.sleep(interval)


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

