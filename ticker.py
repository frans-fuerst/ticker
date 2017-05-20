#!/usr/bin/env python3

import urllib
import json
import sys
import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
import pylab
from pprint import pprint
from datetime import datetime
from urllib.request import urlopen

URL = 'https://poloniex.com/public?command=returnTicker'
BASE = {'BTC', 'ETH', 'XMR', 'USDT'}


def get_ticker() -> str:
    json_data = urlopen(URL).read().decode()
    open('{:%Y.%m.%d-%H.%M.%S}.json'.format(datetime.now()), 'w').write(json_data)
    return json_data

def magic(graph):
    pass

def main():

    graph = nx.DiGraph()

    in_data = json.loads(open(sys.argv[1]).read() if len(sys.argv) > 1 else 
                         get_ticker())

    for d, detail in in_data.items():
        graph.add_edge(*d.split('_'), detail)

    graph.remove_nodes_from(
        (n for n in graph.nodes() 
            if len(graph.in_edges(n)) < 2 and n not in BASE))

    magic(graph)

    pos = nx.spring_layout(graph, k=1.15, iterations=50)
    pos.update({'XMR':  [0.2, 0.5],
                'BTC':  [0.4, 0.5],
                'ETH':  [0.6, 0.5],
                'USDT': [0.8, 0.5]})

    nx.draw_networkx_edge_labels(graph, pos, 
        edge_labels=dict([((u, v), d['last']) for u, v, d in graph.edges(data=True)])
    )
    nx.draw(graph, pos, 
        # edge_color=edge_colors, 
        node_color=[{'BTC': 'g',
                     'USDT':'r',
                     'ETH': 'c',
                     'XMR': 'y'}.get(n, 'w') for n in graph.nodes()], 
        node_size=1500)
    nx.draw_networkx_labels(graph, pos, font_size=12)
    pylab.show()


if __name__ == '__main__':
    main()

