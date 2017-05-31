#!/usr/bin/env python3

__all__ = ['show_gui']

import sys
import os
import signal
import ast
import time
import argparse
import threading
import queue
import logging as log
from PyQt4 import QtGui, QtCore, Qt, uic
import qwt

import trader

HISTORY_LENGTH = 6 * 3600
#HISTORY_LENGTH = 100
UPDATE_INTERVAL_SEC = 1 * 60
MARKETS = (
#        'BTC_XMR',
#        'BTC_FLO',
#        'BTC_ETH',
)

QT_COLORS = [
    QtCore.Qt.green,
    QtCore.Qt.blue,
    QtCore.Qt.red,
    QtCore.Qt.cyan,
    QtCore.Qt.magenta,
    QtCore.Qt.darkBlue,
    QtCore.Qt.darkCyan,
    QtCore.Qt.darkGray,
    QtCore.Qt.darkGreen,
    QtCore.Qt.darkMagenta,
    QtCore.Qt.darkRed,
    QtCore.Qt.darkYellow,
    QtCore.Qt.lightGray,
    QtCore.Qt.gray,
    QtCore.Qt.white,
    QtCore.Qt.black,
    QtCore.Qt.yellow]


class DataPlot(qwt.QwtPlot):

    def __init__(self, *args):
        qwt.QwtPlot.__init__(self, *args)

        self.setCanvasBackground(Qt.Qt.green)
        self.alignScales()

        self.x = [1, 2, 3]
        self.y = [1.0, 2.0, 3.0]

        self.curveR = qwt.QwtPlotCurve("Data Moving Right")
        self.curveR.attach(self)

        self.curveR.setPen(Qt.QPen(Qt.Qt.red))

        mY = qwt.QwtPlotMarker()
        mY.setLabelAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignTop)
        mY.setLineStyle(qwt.QwtPlotMarker.HLine)
        mY.setYValue(0.0)
        mY.attach(self)

        self.enableAxis(qwt.QwtPlot.xBottom, False)
        self.enableAxis(qwt.QwtPlot.yLeft, True)
        # self.setAxisTitle(qwt.QwtPlot.xBottom, "Time (seconds)")
        # self.setAxisTitle(qwt.QwtPlot.yLeft, "Values")

        self.redraw()

    def alignScales(self):
        self.canvas().setFrameStyle(Qt.QFrame.Box | Qt.QFrame.Plain)
        self.canvas().setLineWidth(1)
        for i in range(qwt.QwtPlot.axisCnt):
            scaleWidget = self.axisWidget(i)
            if scaleWidget:
                scaleWidget.setMargin(0)
            scaleDraw = self.axisScaleDraw(i)
            if scaleDraw:
                scaleDraw.enableComponent(
                    qwt.QwtAbstractScaleDraw.Backbone, False)

    def set_data(self, datax, datay):
        self.x, self.y = datax, datay

    def redraw(self):
        self.curveR.setData(self.x, self.y)
        self.replot()


class MarketWidget(QtGui.QWidget):

    close_window = QtCore.pyqtSignal(str)

    def __init__(self, market, api):
        QtGui.QWidget.__init__(self)
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'market.ui'), self)
        self._current_rate = 0.0
        self._trader_api = api
        self._market = market
        self.lbl_market.setText(market)
        self._plot = DataPlot()
        self.layout().addWidget(self._plot)
        #self.tbl_values.verticalHeader().setFixedWidth(160)
        #self.tbl_values.verticalHeader().setResizeMode(QtGui.QHeaderView.Fixed)
        #self.tbl_values.verticalHeader().setDefaultSectionSize(32)
        #self.tbl_values.verticalHeader().setResizeMode(
            #QtGui.QHeaderView.Interactive)

    def threadsafe_update_plot(self):
        log.info('update trade history for %r', self._market)
        data = trader.Api.get_trade_history(*self._market.split('_'), duration=HISTORY_LENGTH)
        if not data: return
        times, rates = trader.get_plot_data(data)
        QtCore.QMetaObject.invokeMethod(
            self, "_set_data",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(list, times),
            QtCore.Q_ARG(list, rates))

    @QtCore.pyqtSlot(list, list)
    def _set_data(self, times, rates):
        self._current_rate = rates[-1]
        self.lbl_current.setText('%.2fh / %f' % ((times[-1] - times[0]) / 3600, self._current_rate))
        self._plot.set_data(times, rates)
        mins, maxs = min(rates), max(rates)
        self._plot.setAxisScale(qwt.QwtPlot.yLeft, min(mins, maxs * 0.9), maxs)
        self._plot.redraw()

    def current_rate(self):
        return self._current_rate


class Trader(QtGui.QMainWindow):

    def __init__(self):
        QtGui.QMainWindow.__init__(self)

        self.setMouseTracking(True)
        self._directory = os.path.dirname(os.path.realpath(__file__))
        uic.loadUi(os.path.join(self._directory, 'trader.ui'), self)
        try:
            self._trader_api = trader.Api(**ast.literal_eval(open('k').read()))
        except FileNotFoundError:
            log.warning('did not find key file - only public access is possible')
            self._trader_api = None
        self._markets = {}

        log.info('initialize personal balances..')
        self._balances = self._trader_api.get_balances()

        self._update_timer = QtCore.QTimer(self)
        self._update_timer.timeout.connect(self._update_timer_timeout)
        self._update_timer.setInterval(UPDATE_INTERVAL_SEC * 1000)
        self._update_timer.start()

        self._worker_thread = threading.Thread(target=self._worker_thread)
        self._tasks = queue.Queue()
        self._worker_thread.start()

        self.pb_check.clicked.connect(self._pb_check_clicked)
        self.pb_buy.clicked.connect(self._pb_buy_clicked)
        self.cb_trade_curr_sell.currentIndexChanged.connect(self._cb_trade_curr_sell_currentIndexChanged)

        self._add_market('USDT_BTC')
        for m in MARKETS:
            self._add_market(m)
        for m in self._balances:
            if m == 'BTC': continue
            self._add_market('BTC_' + m)

        self.show()
        self._update_values()

    def _worker_thread(self):
        while True:
            f = self._tasks.get()
            log.info('got new task..')
            try:
                f()
            except Exception as exc:
                log.error('Exception in worker thread %r', exc)

    def _update_timer_timeout(self):
        log.info('Update timeout')
        self._update_values()

    def _update_values(self):
        log.info('Trigger update')
        for _, w in self._markets.items():
            self._tasks.put(w.threadsafe_update_plot)
        self._tasks.put(self._threadsafe_update_balances)

    def _pb_check_clicked(self):
        self.pb_buy.setEnabled(True)

    def _pb_buy_clicked(self):
        pass

    def _cb_trade_curr_sell_currentIndexChanged(self, index):
        selected = self.cb_trade_curr_sell.itemText(index)
        if not selected: return
        log.info('selected currency to sell: %r', selected)
        self.le_trade_amount.setText(str(self._balances[selected]))

    def _threadsafe_update_balances(self):
        if not self._trader_api: return
        balances = self._trader_api.get_balances()
        eur_price = trader.get_EUR()
        QtCore.QMetaObject.invokeMethod(
            self, "_set_balance_data",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(dict, balances),
            QtCore.Q_ARG(float, eur_price))

    @QtCore.pyqtSlot(dict, float)
    def _set_balance_data(self, balances, eur_price):
        self._balances = balances
        self.cb_trade_curr_sell.clear()
        self.lst_balances.clear()
        for c, a in self._balances.items():
            self.cb_trade_curr_sell.addItem(c)
            self.lst_balances.addItem('%r: %f' % (c, a))

        if not 'USDT_BTC' in self._markets: return

        xbt_rate = self._markets['USDT_BTC'].current_rate()
        self.lbl_XBT_USD.setText('BTC/USD: %.2f' % xbt_rate)
        self.lbl_XBT_EUR.setText('BTC/EUR: %.2f' % (xbt_rate * eur_price))

    def _add_market(self, market):
        if market in self._markets: return
        log.info('add market: %r', market)
        new_item = QtGui.QListWidgetItem()
        new_item.setSizeHint(QtCore.QSize(110, 210))
        new_item.setFlags(QtCore.Qt.ItemIsEnabled)
        new_market = MarketWidget(market, self._trader_api)
        self.lst_markets.addItem(new_item)
        self.lst_markets.setItemWidget(new_item, new_market)
        self._markets[market] = new_market


def show_gui():
    app = QtGui.QApplication(sys.argv)
    _ = Trader()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    return app.exec_()


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='history_server')

    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument("-c", "--allow-cached", action='store_true')
    return parser.parse_args()


def main():
    args = get_args()
    log.basicConfig(level=log.INFO)
    trader.ALLOW_CACHED_VALUES = 'ALLOW' if args.allow_cached else 'NEVER'
    sys.exit(show_gui())


if __name__ == '__main__':
    main()

