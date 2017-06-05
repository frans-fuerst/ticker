#!/usr/bin/env python3

import sys
import os
import signal
import ast
import argparse
import threading
import queue
import time
from pprint import pprint
import json
import logging as log
from PyQt4 import QtGui, QtCore, Qt, uic
import qwt

import trader


class DataPlot(qwt.QwtPlot):

    def __init__(self, *args):
        qwt.QwtPlot.__init__(self, *args)

        self.enableAxis(qwt.QwtPlot.xBottom, False)
        self.enableAxis(qwt.QwtPlot.yLeft, True)

        self.axisWidget(qwt.QwtPlot.yLeft).scaleDraw().setMinimumExtent(100)


    def set_data(self, datax, datay, pen):
        curve = qwt.QwtPlotCurve("Curve 1")
        curve.setData(datax, datay)
        curve.setPen(pen)
        curve.attach(self)

    def set_y_scale(self, smin, smax):
        self.setAxisScale(qwt.QwtPlot.yLeft, smin, smax)

    def redraw(self):
        self.replot()


def clear(data, factor):
    if not data: return data
    fr = 1 / factor
    result = [data[0]]
    for i in range(len(data) - 2):
        l, m, r = data[i:i+3]
        a = (l + r) / 2
        q = m / a if a != 0. else 1.0
        e = m if fr < q < factor else a
        result.append(e)
    result.append(data[-1])
    return result


def ema(data, a):
    n = data[0]
    result = []
    an = 1 - a
    for x in data:
        n = a * n + an * x
        result.append(n)
    return result


def vema(dataa, datab, a):
    smooth_dataa = ema(dataa, a)
    smooth_datab = ema(datab, a)
    return [a / b for a, b in zip(smooth_dataa, smooth_datab)]


class GraphUI(QtGui.QWidget):

    def __init__(self):
        super().__init__()
        self.setLayout(QtGui.QVBoxLayout())

        try:
            data = json.load(open('data'))
        except FileNotFoundError:
            history = trader.Api.get_trade_history(
                primary='BTC', coin='XMR', duration=6 * 3600) #, duration=3600)
            data = [(float(e['total']),
                     float(e['amount']),
                     time.mktime(e['date'].timetuple()) - time.time())
                    for e in history]
            json.dump(data, open('data', 'w'))

 #       data = data[28:200]

        totals = [e[0] for e in data]
        amounts = [e[1] for e in data]
        rates = [e[0] / e[1] for e in data]
        times = [e[2] for e in data]

        rates_clean = clear(rates, 1.01)

        rates_maverage = ema(rates, 0.99)
        rates_vema = vema(totals, amounts, 0.98)

        rates_old = trader.get_maverage(trader.clean(rates, 1.1), 0.02)
        rates_old = trader.get_maverage(rates, 0.02)


        plot = DataPlot()

        self.layout().addWidget(plot)

        self.setGeometry(200, 200, 1100, 650)

        plot.set_data(times, rates, Qt.QPen(Qt.Qt.black, 1, Qt.Qt.SolidLine))
        #        plot.set_data(times, rates_clean, Qt.QPen(Qt.Qt.black, 2, Qt.Qt.SolidLine))
        #        plot.set_data(times, rates_maverage, Qt.QPen(Qt.Qt.blue, 2, Qt.Qt.SolidLine))
        plot.set_data(times, rates_old, Qt.QPen(Qt.Qt.blue, 2, Qt.Qt.SolidLine))
        plot.set_data(times, rates_vema, Qt.QPen(Qt.Qt.red, 2, Qt.Qt.SolidLine))

        m = max(rates)
        plot.set_y_scale(0.9 * m, m)
        plot.redraw()

        self.show()


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='history_server')

    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument("-c", "--allow-cached", action='store_true')
    return parser.parse_args()


def main():
    args = get_args()

    log.basicConfig(level=log.INFO)
    trader.ALLOW_CACHED_VALUES = 'ALLOW' if args.allow_cached else 'NEVER'
    app = QtGui.QApplication(sys.argv)
    _ = GraphUI()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

