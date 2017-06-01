#!/usr/bin/env python3

__all__ = ['show_gui']

import sys
import os
import signal
import ast
import argparse
import threading
import queue
import time
import logging as log
from PyQt4 import QtGui, QtCore, Qt, uic
import qwt

import trader

GRAPH_HEIGHT = 140
HISTORY_LENGTH = 6 * 3600
#HISTORY_LENGTH = 100
UPDATE_INTERVAL_SEC = 3 * 60
MARKETS = (
    'BTC_XMR',   # Monero
    'BTC_FLO',   # Florin
    'BTC_ETH',   # Ethereum
    'BTC_XRP',   # Ripple
    'BTC_ETC',   # Ethereum Classic
    'BTC_LTC',   # Litecoin
#    'BTC_DASH',  # Dash
#    'BTC_GNT',   # Golem
    'BTC_BURST',   # Burst
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
        scaleWidget = self.axisWidget(qwt.QwtPlot.yLeft)
        #scaleWidget.setFixedWidth(200)
        #d = scaleWidget.scaleDraw()
        #d.minimumExtent
        scaleWidget.scaleDraw().setMinimumExtent(100)

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
        class LogHandler(log.Handler):
            def __init__(self, parent):
                super().__init__()
                self._parent = parent

            def emit(self, record):
                QtCore.QMetaObject.invokeMethod(
                    self._parent, "_log_message",
                    QtCore.Qt.QueuedConnection,
                    QtCore.Q_ARG(dict, record.__dict__),
                )

        QtGui.QMainWindow.__init__(self)
        log.getLogger().addHandler(LogHandler(self))

        self.setMouseTracking(True)
        self._directory = os.path.dirname(os.path.realpath(__file__))
        uic.loadUi(os.path.join(self._directory, 'trader.ui'), self)
        try:
            self._trader_api = trader.Api(**ast.literal_eval(open('k').read()))
            log.info('initialize personal balances..')
        except FileNotFoundError:
            log.warning('did not find key file - only public access is possible')
            self._trader_api = None

        self._balances = self._fetch_balances()
        self._markets = {}
        self._last_update = None

        self._update_timer = QtCore.QTimer(self)
        self._update_timer.timeout.connect(self._update_timer_timeout)
        self._update_timer.setInterval(UPDATE_INTERVAL_SEC * 1000)
        self._update_timer.start()

        time_info_timer = QtCore.QTimer(self)
        time_info_timer.timeout.connect(self._time_info_timer_timeout)
        time_info_timer.setInterval(1000)
        time_info_timer.start()

        self._worker_thread = threading.Thread(target=self._worker_thread_fn)
        self._tasks = queue.Queue()
        self._worker_thread.start()

        self.pb_check.clicked.connect(self._pb_check_clicked)
        self.pb_buy.clicked.connect(self._pb_buy_clicked)
        self.cb_trade_curr_sell.currentIndexChanged.connect(self._cb_trade_curr_sell_currentIndexChanged)
        self.cb_trade_curr_buy.currentIndexChanged.connect(self._cb_trade_curr_buy_currentIndexChanged)
        self.le_trade_amount.textChanged.connect(self._le_trade_amount_textChanged)

        self._add_market('USDT_BTC')
        for m in MARKETS:
            self._add_market(m)
        for m in self._balances:
            if m == 'BTC': continue
            self._add_market('BTC_' + m)

        self.show()
        self._update_values()

    @QtCore.pyqtSlot(dict)
    def _log_message(self, record):
        self.lst_log.addItem(record['message'])
        self.lst_log.scrollToBottom()

    def closeEvent(self, event):
        self._tasks.put(None)
        self._worker_thread.join()

    def _worker_thread_fn(self):
        while True:
            f = self._tasks.get()
            if f is None:
                return
            log.debug('got new task..')
            while True:
                try:
                    f()
                    break
                except Exception as exc:
                    log.error('Exception in worker thread %r', exc)

    def _fetch_balances(self):
        if not self._trader_api: return {}
        return self._trader_api.get_balances()

    def _update_timer_timeout(self):
        log.info('Update timeout')
        self._update_values()

    def _time_info_timer_timeout(self):
        if not self._last_update: return
        self.lbl_last_update.setText('%d' % (time.time() - self._last_update))

    def _update_values(self):
        log.info('Trigger update')
        for _, w in self._markets.items():
            self._tasks.put(w.threadsafe_update_plot)
        self._tasks.put(self._threadsafe_update_balances)
        def update_time():
            self._last_update = time.time()
        self._tasks.put(update_time)


    def _pb_check_clicked(self):
        self.pb_buy.setEnabled(False)
        try:
            suggested_rate = self._place_order(check=True)
            self.le_rate.setText(str(suggested_rate))
            self.pb_buy.setEnabled(True)
        except (RuntimeError, ValueError) as exc:
            log.error('cannot place order: %s', exc)

    def _pb_buy_clicked(self):
        try:
            self._place_order(check=False)
        except (RuntimeError, ValueError) as exc:
            log.error('cannot place order: %s', exc)
        self._threadsafe_update_balances()

    def _place_order(self, *, check: bool):
        sell = (float(self.le_trade_amount.text()),
                self.cb_trade_curr_sell.currentText())
        buy = self.cb_trade_curr_buy.currentText()
        log.info('place order: sell=%r buy=%r check=%r', sell, buy, check)
        rate = None if check else float(self.le_rate.text())
        return self._trader_api.place_order(
            sell=sell, buy=buy, rate=rate, fire=not check)

    def _le_trade_amount_textChanged(self):
        self.pb_buy.setEnabled(False)

    def _cb_trade_curr_sell_currentIndexChanged(self, index):
        #self.pb_buy.setEnabled(False)
        selected = self.cb_trade_curr_sell.itemText(index)
        if not selected: return
        log.info('selected currency to sell: %r', selected)
        self.le_trade_amount.setText(str(self._balances[selected]))

    def _cb_trade_curr_buy_currentIndexChanged(self, index):
        #self.pb_buy.setEnabled(False)
        selected = self.cb_trade_curr_buy.itemText(index)
        if not selected: return

    def _threadsafe_update_balances(self):
        if not self._trader_api: return
        balances = self._trader_api.get_balances()
        eur_price = trader.get_EUR()
        orders = self._trader_api.get_open_orders()
        QtCore.QMetaObject.invokeMethod(
            self, "_set_balance_data",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(dict, balances),
            QtCore.Q_ARG(float, eur_price),
            QtCore.Q_ARG(dict, orders),
        )

    @QtCore.pyqtSlot(dict, float, dict)
    def _set_balance_data(self, balances, eur_price, orders):
        self._balances = balances
        self.cb_trade_curr_sell.clear()
        self.cb_trade_curr_buy.clear()
        self.lst_balances.clear()
        self.lst_orders.clear()

        xbt_usd_rate = self._markets['USDT_BTC'].current_rate()
        btc_total = 0.
        eur_total = 0.
        for c, a in sorted(self._balances.items()):
            self.cb_trade_curr_sell.addItem(c)
            _m = 'BTC_%s' % c
            _btc_rate = (
                1. if c == 'BTC' else
                self._markets[_m].current_rate() if _m in self._markets else
                0.)
            _add_btc = a * _btc_rate
            _add_eur = _add_btc * xbt_usd_rate * eur_price
            btc_total += _add_btc
            eur_total += _add_eur
            self.lst_balances.addItem('%r: %8.4f  ~BTC %7.2f  ~EUR %7.2f' % (
                c, a, _add_btc, _add_eur ))

        self.cb_trade_curr_buy.addItem('BTC')
        for c in sorted(self._trader_api.get_markets()['BTC']):
            self.cb_trade_curr_buy.addItem(c)

        if not 'USDT_BTC' in self._markets: return

        self.lbl_XBT_USD.setText('%.2f' % xbt_usd_rate)
        self.lbl_XBT_EUR.setText('%.2f' % (xbt_usd_rate * eur_price))
        self.lbl_bal_BTC.setText('%.4f' % (btc_total))
        self.lbl_bal_EUR.setText('%.4f' % (eur_total))
        log.info('orders: %r', orders)
        for o in orders.items():
            self.lst_orders.addItem(str(o))

    def _add_market(self, market):
        if market in self._markets: return
        log.info('add market: %r', market)
        new_item = QtGui.QListWidgetItem()
        new_item.setSizeHint(QtCore.QSize(110, GRAPH_HEIGHT))
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

