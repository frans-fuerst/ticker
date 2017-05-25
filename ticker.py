#!/usr/bin/env python3

import os
import json
import sys
import networkx as nx
import pylab
import time
import argparse
from pprint import pprint
from datetime import datetime
from urllib.request import urlopen
from operator import mul
from functools import reduce

URL = 'https://poloniex.com/public?command=returnTicker'
BASE = {'BTC', 'ETH', 'XMR', 'USDT'}
TIMESTAMP_FORMAT = '%Y.%m.%d-%H.%M.%S.json'


def get_ticker() -> str:
    json_data = urlopen(URL).read().decode()
    open('{:%Y.%m.%d-%H.%M.%S}.json'.format(datetime.now()), 'w').write(json_data)
    return json_data


def get_factor(graph, path):
    def get_transition_factor(c1, c2):
        if graph.has_edge(c1, c2):
            return float(graph.get_edge_data(c1, c2)['last'])
        elif graph.has_edge(c2, c1):
            return 1.0 / float(graph.get_edge_data(c2, c1)['last'])
        else:
            raise ValueError('%r %r' % (c1, c2))
    return reduce(mul, map(get_transition_factor, path, path[1:]))


def magic(graph):
    result = {}
    for p in sorted(graph.nodes()):
        if p in BASE: continue
        result[p] = {}
        cs = [c for c, _ in graph.in_edges(p)]
        for c1 in sorted(cs):
            path = (c1, p)
            direct = get_factor(graph, path)
            result[p][path] = (direct, 0.0)
            for c2 in sorted(cs):
                if c1 == c2: continue
                try:
                    path = (c1, c2, p)
                    indirect = get_factor(graph, path)
                    factor = (1 - indirect / direct)
                    result[p][path] =  (indirect, 100 * factor)
                except ValueError:
                    pass
    return result


def get_ticker(source: str) -> dict:

    graph = nx.DiGraph()

    in_data = json.loads(open(source).read() if source else
                         get_ticker())

    graph.add_edges_from((*d.split('_'), in_data[d]) for d in sorted(in_data))

    graph.remove_nodes_from(
        (n for n in graph.nodes()
            if len(graph.in_edges(n)) < 2 and n not in BASE))

    positions = nx.spring_layout(graph, k=1.15, iterations=50)
    positions.update({'XMR':  [0.2, 0.5],
                      'BTC':  [0.4, 0.5],
                      'ETH':  [0.6, 0.5],
                      'USDT': [0.8, 0.5]})

    nx.draw_networkx_edge_labels(graph, positions,
        edge_labels=dict([((u, v), d['last'])
                            for u, v, d in graph.edges(data=True)]))
    nx.draw(graph, positions,
        #edge_color={},
        node_color=[{'BTC': 'g',
                     'USDT':'r',
                     'ETH': 'c',
                     'XMR': 'y'}.get(n, 'w') for n in graph.nodes()],
        node_size=1500)
    nx.draw_networkx_labels(graph, positions, font_size=12)

    return magic(graph)


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='ticker')

    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument("--no-graph", '-n', action='store_true')
    parser.add_argument('source')
    return parser.parse_args()


def main():
    args = get_args()
    if os.path.isdir(args.source):
        
        for f in os.listdir():
            if not '.json' in f: continue
            pprint(get_ticker(f))
            print(time.strptime(f, TIMESTAMP_FORMAT))
    elif os.path.isfile(args.source):
        pprint(get_ticker(args.source))
        if not args.no_graph:
            pylab.show()


if __name__ == '__main__':
    main()

