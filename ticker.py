#!/usr/bin/env python3

import json
import sys
import networkx as nx
import pylab
from pprint import pprint
from datetime import datetime
from urllib.request import urlopen
from operator import mul
from functools import reduce

URL = 'https://poloniex.com/public?command=returnTicker'
BASE = {'BTC', 'ETH', 'XMR', 'USDT'}


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


def main():

    graph = nx.DiGraph()

    in_data = json.loads(open(sys.argv[1]).read() if len(sys.argv) > 1 else
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

    pprint(magic(graph))

    if '-n' not in sys.argv:
        pylab.show()


if __name__ == '__main__':
    main()

