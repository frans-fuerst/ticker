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

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import trader


class DataPlot(qwt.QwtPlot):

    def __init__(self, *args):
        qwt.QwtPlot.__init__(self, *args)

        self.enableAxis(qwt.QwtPlot.xBottom, True)
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


class GraphUI(QtGui.QWidget):

    def __init__(self):
        super().__init__()
        self.setLayout(QtGui.QVBoxLayout())

        now = time.time()

        self.th = trader.TradeHistory('BTC_ETH', step_size_sec=6*3600)
        self.th.load()
        if self.th.get_duration() < 10 * 3600:
            self.th.fetch_next()
            self.th.save()

#        print(self.th.count(), self.th.get_duration()/3600)

        data = self.th.data() #[-10000:]

#        [print(d) for d in data]

        print((data[-1]['time']-data[0]['time']) / 3600)

        totals = [e['total'] for e in data]
        amounts = [e['amount'] for e in data]
        rates = [e['total'] / e['amount'] for e in data]
        times = [e['time'] - now for e in data]
        full = [(e['time'] - now, e['total'], e['amount'], e['total'] / e['amount']) for e in data]

#        [print('%.2f, %11.8f, %11.8f, %9.9f' % d) for d in full]

        #rates_vema_slow = trader.vema(totals, amounts, 0.001)
        #rates_vema_fast = trader.vema(totals, amounts, 0.004)

        candlestick_data = self.th.rate_buckets()
        times2 = [e['time'] - now for e in candlestick_data]
        rates_sell = [e['total_sell'] / e['amount_sell'] for e in candlestick_data]
        rates_buy = [e['total_buy'] / e['amount_buy'] for e in candlestick_data]
        amounts_sell = [e['amount_sell'] for e in candlestick_data]
        totals_sell = [e['total_sell'] for e in candlestick_data]

        rates_vema_fast = trader.vema(totals_sell, amounts_sell, 0.1)
        rates_vema_slow = trader.vema(totals_sell, amounts_sell, 0.1)


        plot = DataPlot()
        self.layout().addWidget(plot)
        self.setGeometry(200, 200, 1100, 650)

        plot.set_data(times, rates, Qt.QPen(Qt.Qt.gray, 1, Qt.Qt.SolidLine))

        plot.set_data(times2, rates_sell, Qt.QPen(Qt.Qt.blue, 2, Qt.Qt.SolidLine))
        plot.set_data(times2, rates_buy, Qt.QPen(Qt.Qt.red, 2, Qt.Qt.SolidLine))
        #plot.set_data(times2, rates_vema_fast, Qt.QPen(Qt.Qt.red, 2, Qt.Qt.SolidLine))
        #plot.set_data(times2, rates_vema_slow, Qt.QPen(Qt.Qt.blue, 2, Qt.Qt.SolidLine))

        m = max(rates)
#        plot.set_y_scale(0.8 * m, m)
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

