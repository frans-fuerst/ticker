#!/usr/bin/env python3

import sys
import os
import signal
import ast
import argparse
import threading
import queue
import time
import traceback
import logging as log
from PyQt4 import QtGui, QtCore, Qt, uic
import qwt
from enum import IntEnum

import mftl
import mftl.util
import mftl.px
from mftl.util import json_mod
from utils import toggle_profiling


class DataPlot(qwt.QwtPlot):

    def __init__(self, *args):
        qwt.QwtPlot.__init__(self, *args)

        self.alignScales()

        self._curve_rates = qwt.QwtPlotCurve()
        self._curve_rates.attach(self)

        self._curve_rates.setPen(Qt.QPen(Qt.Qt.red))

        self._marker = qwt.QwtPlotMarker()
        self._marker.setLabelAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignTop)
        self._marker.setLineStyle(qwt.QwtPlotMarker.HLine)
        self._marker.setYValue(0.0)
        self._marker.attach(self)

        self.enableAxis(qwt.QwtPlot.xBottom, False)
        self.enableAxis(qwt.QwtPlot.yLeft, True)
        # self.setAxisTitle(qwt.QwtPlot.xBottom, "Time (seconds)")
        # self.setAxisTitle(qwt.QwtPlot.yLeft, "Values")
        self.setCanvasBackground(Qt.Qt.green)

        self.redraw()

    def alignScales(self):
        self.canvas().setFrameStyle(Qt.QFrame.Box | Qt.QFrame.Plain)
        scaleWidget = self.axisWidget(qwt.QwtPlot.yLeft)
        scaleWidget.scaleDraw().setMinimumExtent(80)

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
        self._curve_rates.setData(datax, datay)

    def set_marker(self, value):
        self._marker.setYValue(value)

    def redraw(self):
        self.replot()


class MarketWidgetItem(QtGui.QListWidgetItem):
    def __init__(self, market_widget, list_widget):
        super().__init__()
        self._market_widget = market_widget
        list_widget.addItem(self)
        list_widget.setItemWidget(self, market_widget)
        self.setFlags(QtCore.Qt.ItemIsEnabled)

    def __lt__(self, other):
        return (self._market_widget.trend() < other._market_widget.trend()
                if isinstance(other, MarketWidgetItem) else
                super().__lt__(other))

    def set_height(self, height):
        self.setSizeHint(QtCore.QSize(110, height))


class MarketWidget(QtGui.QWidget):

    updated = QtCore.pyqtSignal()

    def __init__(self, trade_history, api):
        super().__init__()
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'market.ui'), self)

        self._trade_history = trade_history
        self._trader_api = api

        self._current_vema_rate = 0.
        self._current_trend = 0.
        self.lbl_market.setText(self._trade_history.name())
        self.lbl_currencies.setText(self._trade_history.friendly_name())
        self._plot = DataPlot()
        self._history_length = 100
        self._marker_value = None
        self.frm_main.layout().addWidget(self._plot)
        self._trade_history.load()

    def threadsafe_update_plot(self):
        log.info('update market trades for %r', self._trade_history.name())
        if not self._trade_history.fetch_next(api=self._trader_api):
            return
        times, rates = self._trade_history.get_plot_data(0.005)
        if not times:
            return
        QtCore.QMetaObject.invokeMethod(
            self, "_set_data", QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(list, times),
            QtCore.Q_ARG(list, rates))

    def trend(self):
        return self._current_trend

    @QtCore.pyqtSlot(list, list)
    def _set_data(self, times, rates_av):
        self._current_vema_rate = rates_av[-1]
        self._current_trend = rates_av[-1] / rates_av[0] - 1.
        self.lbl_rate_vema.setText('%.9f' % self._current_vema_rate)
        self.lbl_rate.setText('%.9f' % self._trade_history.last_rate())
        self.lbl_duration.setText('%.2fh' % ((times[-1] - times[0]) / 3600))
        self.lbl_age.setText('%ds' % (time.time() - self._trade_history.last_time()))
        self.lbl_trend.setText('%.2f%%' % (100 * self._current_trend))

        self._plot.set_data(times, rates_av)
        mins, maxs = min(rates_av), max(rates_av)
        if self._marker_value:
            maxs = max(maxs, self._marker_value)
            mins = min(mins, self._marker_value)
        self._plot.setAxisScale(qwt.QwtPlot.yLeft, min(mins, maxs * 0.9), maxs)
        self.redraw()
        self.updated.emit()

    def redraw(self):
        self._plot.redraw()

    def set_marker(self, value):
        self._marker_value = value
        self._plot.set_marker(self._marker_value)

    def current_rate(self):
        return self._current_vema_rate

    def shutdown(self):
        self._trade_history.save()


class Priorities(IntEnum):
    Critical = 0
    Order = 1
    Init = 2
    Balances = 3
    Low = 4
    Lowest = 5


class Trader(QtGui.QMainWindow):
    class Task:
        def __init__(self, fn, priority, retry: bool):
            self.fn = fn
            self.priority = priority
            self.retry = retry

        def __lt__(self, other):
            return self.priority < other.priority

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
        self._config = self._load_config('config')
        if 'proxies' in self._config:
            mftl.util.set_proxies(self._config['proxies'])

        self._trader_api = self._get_trader()
        self._data = mftl.TraderData()
        self._balances_dirty = True
        self._markets = {}

        self._update_timer = QtCore.QTimer(self)
        self._update_timer.timeout.connect(self._update_timer_timeout)
        self._update_timer.setInterval(self._config['update_interval_sec'] * 1000)
        self._update_timer.start()

        time_info_timer = QtCore.QTimer(self)
        time_info_timer.timeout.connect(self._time_info_timer_timeout)
        time_info_timer.setInterval(1000)
        time_info_timer.start()

        self._worker_thread = threading.Thread(target=self._worker_thread_fn)
        self._tasks = queue.PriorityQueue()
        self._worker_thread.start()

        self.pb_check.clicked.connect(self._pb_check_clicked)
        self.pb_place_order.clicked.connect(self._pb_place_order_clicked)
        self.pb_refresh.clicked.connect(self._pb_refresh_clicked)
        self.pb_update_balances.clicked.connect(self._pb_update_balances_clicked)
        self.cb_trade_curr_sell.currentIndexChanged.connect(self._cb_trade_curr_sell_currentIndexChanged)
        self.cb_trade_curr_buy.currentIndexChanged.connect(self._cb_trade_curr_buy_currentIndexChanged)
        self.le_trade_amount.textChanged.connect(self._le_trade_amount_textChanged)
        self.pb_profile.clicked.connect(self._pb_profile_clicked)
        self.pb_stacktrace.clicked.connect(self._pb_stacktrace_clicked)

        def setup_table(widget):
            for i in range(widget.columnCount()):
                widget.horizontalHeader().setResizeMode(
                    i, QtGui.QHeaderView.ResizeToContents)

        # sort by time
        self.tbl_order_history.sortItems(0, QtCore.Qt.DescendingOrder)
        # sort by EUR value
        self.tbl_balances.sortItems(4, QtCore.Qt.DescendingOrder)
        self.tbl_open_orders.sortItems(2, QtCore.Qt.DescendingOrder)
        self.le_suggested_rate_factor.setText(str(self._config['suggested_rate_factor']))

        setup_table(self.tbl_balances)
        setup_table(self.tbl_open_orders)
        setup_table(self.tbl_order_history)

        self._add_market('USDT_BTC', self.lst_primary_coins)
        for m in self._config['markets']:
            self._add_market(m, self.lst_markets)

        self.show()

        self._update_values()

    def _update_values(self):
        if not self._tasks.empty():
            log.warning("task not done yet - I'll come back later")
            return

        if not self._data.available_markets():
            # todo: update
            self._put_task(self._threadsafe_fetch_markets, Priorities.Init)

        if (not self._data.trade_history() or
            not self._data.balances() or
                self._balances_dirty):
            self._balances_dirty = False
            self._put_task(self._threadsafe_fetch_orders, Priorities.Balances)
            self._put_task(self._threadsafe_fetch_balances, Priorities.Balances)

        for _, w in self._markets.items():
            self._put_task(w.threadsafe_update_plot, Priorities.Low)

        # todo
        self._put_task(self._threadsafe_display_balances, 1)

    def _load_config(self, filename):
        result = {'graph_height':   140,
                  'history_length_h': 4,
                  'update_interval_sec': 180,
                  'suggested_rate_factor': 1.0,
                  'markets': (
                      'BTC_ETC', # 'Ethereum Classic
                      #'BTC_XMR', #'Monero
                  )}
        try:
            result.update(ast.literal_eval(open(filename).read()))
        except FileNotFoundError:
            log.warning("you don't have a 'config' file, use default values")
        return result

    def _get_trader(self):
        try:
            return mftl.px.PxApi(**ast.literal_eval(open('k').read()))
        except FileNotFoundError:
            log.warning('did not find key file - only public access is possible')
            return None

    @QtCore.pyqtSlot(dict)
    def _log_message(self, record):
        self.lst_log.addItem(
            record['message'] if 'message' in record else record['msg'])
        self.lst_log.scrollToBottom()

    def closeEvent(self, _):
        log.info('got close event, wait for worker to finish..')
        self._put_task(None, Priorities.Critical)
        self._worker_thread.join()
        t1 = time.time()
        self._persist()
        log.info('saving trade history took %.2fs', time.time() - t1)
        log.info('bye bye!')

    def _load(self):
        self._data.load()
        self._handle_order_data()

    def _persist(self):
        for _, m in self._markets.items():
            m.shutdown()


    def _put_task(self, fn, priority, retry=True):
        self._tasks.put(Trader.Task(fn, priority, retry))

    def _worker_thread_fn(self):
        def multiple_try(fn, times):
            for _ in range(times):
                try:
                    fn()
                    return
                except Exception as exc:
                    traceback.print_exc()
                    log.warning('Exception in worker thread: %r', exc)
            raise Exception()

        while True:
            task = self._tasks.get()
            if task.fn is None:
                log.info('exit _worker_thread_fn()')
                return
            log.debug('got new task..')
            try:
                multiple_try(task.fn, 3 if task.retry else 1)
            except Exception as exc:
                log.error('giving up trying to call %r', task.fn)
                return

    def _update_timer_timeout(self):
        if not self._worker_thread.is_alive(): return
        log.info('trigger updates')
        self._update_values()

    def _time_info_timer_timeout(self):
        self.lbl_last_update.setText('%d' % self._tasks.qsize())

    def _pb_refresh_clicked(self):
        self._update_values()

    def _pb_stacktrace_clicked(self):
        import faulthandler
        faulthandler.dump_traceback(file=sys.stdout, all_threads=True)

    def _pb_profile_clicked(self):
        log.info('toggle profiling')
        toggle_profiling(clock_type='cpu')

    def _pb_update_balances_clicked(self):
        self._put_task(self._threadsafe_fetch_orders, Priorities.Balances)
        self._put_task(self._threadsafe_fetch_balances, Priorities.Balances)

    def _pb_check_clicked(self):
        self.pb_place_order.setEnabled(False)
        sell = (float(self.le_trade_amount.text()),
                self.cb_trade_curr_sell.currentText())
        buy = self.cb_trade_curr_buy.currentText()
        speed_factor = float(self.le_suggested_rate_factor.text())
        log.info('create order from: sell=%r buy=%r speed_factor=%f',
                 sell, buy, speed_factor)
        try:
            order = self._data.suggest_order(sell=sell, buy=buy,
                suggestion_factor=speed_factor)
        except (RuntimeError, ValueError) as exc:
            log.error('cannot place order: %s', exc)
            return

        self.le_order_market.setText(order['market'])
        self.le_order_amount.setText(str(order['amount']))
        self.le_order_rate.setText(str(order['rate']))
        self.cb_order_action.setCurrentIndex(
            self.cb_order_action.findText(order['action']))
        self.pb_place_order.setEnabled(True)

    def _pb_place_order_clicked(self):
        order = {'market': self.le_order_market.text(),
                 'action': self.cb_order_action.currentText(),
                 'rate': float(self.le_order_rate.text()),
                 'amount': float(self.le_order_amount.text()),
                 'speed_factor': float(self.le_suggested_rate_factor.text()),
                 }

        self._put_task(
            lambda: self._threadsafe_place_order(order),
            Priorities.Critical,
            retry=False)

    def _threadsafe_place_order(self, order):
        log.info('place order: %r', order)
        try:
            result = self._trader_api.place_order(
                market=order['market'],
                action=order['action'],
                rate=order['rate'],
                amount=order['amount'])
        except (RuntimeError, ValueError) as exc:
            log.error('cannot place order: %s', exc)
            return

        result.update({'speed_factor': order['speed_factor'],
                       'time': time.time()})
        QtCore.QMetaObject.invokeMethod(
            self, "_handle_order_result", QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(dict, result))

    @QtCore.pyqtSlot(dict)
    def _handle_order_result(self, order_result):
        def save_order(order):
            if not order: return
            try:
                orders = json_mod.loads(open('orders').read())
            except FileNotFoundError:
                orders = []
            orders.append(order)
            open('orders', 'w').write(json_mod.dumps(orders))

        save_order(order_result)
        self._balances_dirty = True
        # self._put_task(self._threadsafe_fetch_balances, 1)

    def _le_trade_amount_textChanged(self):
        self.pb_place_order.setEnabled(False)

    def _cb_trade_curr_sell_currentIndexChanged(self, index):
        #self.pb_place_order.setEnabled(False)
        selected = self.cb_trade_curr_sell.itemText(index)
        if not selected: return
        log.info('selected currency to sell: %r', selected)
        self.le_trade_amount.setText(str(self._data.balances(selected)))

    def _cb_trade_curr_buy_currentIndexChanged(self, index):
        #self.pb_place_order.setEnabled(False)
        selected = self.cb_trade_curr_buy.itemText(index)
        if not selected: return

    def _threadsafe_fetch_markets(self):
        log.info('fetch ticker info..')
        self._data.update_available_markets(mftl.px.PxApi)

        # ticker = mftl.px.PxApi.get_ticker()
        # coins = mftl.px.PxApi.extract_coin_data(ticker)
        # markets = set(ticker.keys())
        QtCore.QMetaObject.invokeMethod(
            self, "_handle_markets", QtCore.Qt.QueuedConnection)

    def _set_cb_items(self, combo_box, items):
        old_items = set(combo_box.itemText(i) for i in range(combo_box.count()))
        if set(items) == old_items: return
        combo_box.clear()
        for c in sorted(items):
            combo_box.addItem(c)

    @QtCore.pyqtSlot()
    def _handle_markets(self):
        self._set_cb_items(self.cb_trade_curr_buy,
                           {'BTC'} | self._data.available_coins()['BTC'])

        try:
            last_markets = set(json_mod.loads(open('last_markets').read()))
        except FileNotFoundError:
            last_markets = set()
        if self._data.available_markets() - last_markets:
            if QtGui.QMessageBox.question(
                    self, 'New Markets!!!11!!',
                    "Be sure to buy coins of %r\n\nSave markets?" % (
                        self._data.available_markets() - last_markets),
                    QtGui.QMessageBox.Ok, QtGui.QMessageBox.No
                    ) == QtGui.QMessageBox.Ok:
                open('last_markets', 'w').write(
                    json_mod.dumps(list(self._data.available_markets())))

    def _threadsafe_fetch_balances(self):
        if not self._trader_api: return
        log.info("update balances..")
        self._data.update_balances(self._trader_api)
        self._data.update_eur()
        QtCore.QMetaObject.invokeMethod(
            self, "_handle_balance_data", QtCore.Qt.QueuedConnection)

    @QtCore.pyqtSlot()
    def _handle_balance_data(self):
        self._display_balances()

    def _threadsafe_display_balances(self):
        QtCore.QMetaObject.invokeMethod(
            self, "_display_balances", QtCore.Qt.QueuedConnection)

    @QtCore.pyqtSlot()
    def _display_balances(self):
        if not self._data.balances(): return

        for m in self._data.balances():
            if m == 'BTC': continue
            self._add_market('BTC_' + m, self.lst_markets)

        self._set_cb_items(self.cb_trade_curr_sell, self._data.balances().keys())

        self.tbl_balances.setSortingEnabled(False)
        self.tbl_balances.setRowCount(len(self._data.balances()))

        xbt_usd_rate = self._markets['USDT_BTC'].current_rate()
        btc_total = 0.
        eur_total = 0.
        i = 0
        for c, a in self._data.balances().items():
            _m = 'BTC_%s' % c
            _btc_rate = (
                1. if c == 'BTC' else
                self._markets[_m].current_rate() if _m in self._markets else
                0.)
            _add_btc = a * _btc_rate
            _add_eur = _add_btc * xbt_usd_rate * self._data.eur_price()
            btc_total += _add_btc
            eur_total += _add_eur
            self.tbl_balances.setItem(i, 0, QtGui.QTableWidgetItem('%s' % c))
            self.tbl_balances.setItem(i, 1, QtGui.QTableWidgetItem('%10.5f' % a))
            self.tbl_balances.setItem(i, 2, QtGui.QTableWidgetItem('%13.8f' % _btc_rate))
            self.tbl_balances.setItem(i, 3, QtGui.QTableWidgetItem('%10.5f' % _add_btc))
            self.tbl_balances.setItem(i, 4, QtGui.QTableWidgetItem('%10.5f' % _add_eur))
            i += 1
        self.tbl_balances.setSortingEnabled(True)

        if not 'USDT_BTC' in self._markets: return

        self.lbl_XBT_USD.setText('%.2f' % xbt_usd_rate)
        self.lbl_XBT_EUR.setText('%.2f' % (xbt_usd_rate * self._data.eur_price()))
        self.lbl_bal_BTC.setText('%.4f' % (btc_total))
        self.lbl_bal_EUR.setText('%.4f' % (eur_total))

    def _threadsafe_fetch_orders(self):
        if not self._trader_api: return
        log.info("update own orders..")

        self._data.update_trade_history(self._trader_api)
        self._data.update_open_orders(self._trader_api)
        QtCore.QMetaObject.invokeMethod(
            self, "_handle_order_data", QtCore.Qt.QueuedConnection)

    @QtCore.pyqtSlot()
    def _handle_order_data(self):
        self._fill_order_table(self.tbl_open_orders, self._data.open_orders(), cancel_button=True)
        self._fill_order_table(self.tbl_order_history, self._data.trade_history())
        for m, history in self._data.trade_history().items():
            for h in history:
                if h['type'] == 'buy' and m in self._markets:
                    self._markets[m].set_marker(
                        float(h['total']) / float(h['amount']))
                    self._markets[m].redraw()
                    break
        if self._data.open_orders():
            self._balances_dirty = True

    def _fill_order_table(self, table_widget, orders, cancel_button=False):
        table_widget.setSortingEnabled(False)
        table_widget.setRowCount(
            sum(len(v) for k, v in orders.items()))
        i = 0
        for c, corder in orders.items():
            for order in corder:
                table_widget.setItem(i, 0, QtGui.QTableWidgetItem(order['date']))
                table_widget.setItem(i, 1, QtGui.QTableWidgetItem(c))
                table_widget.setItem(i, 2, QtGui.QTableWidgetItem(order['type']))
                table_widget.setItem(i, 3, QtGui.QTableWidgetItem('%.8f' % order['amount']))
                table_widget.setItem(i, 4, QtGui.QTableWidgetItem('%.8f' % order['total']))
                table_widget.setItem(i, 5, QtGui.QTableWidgetItem('%.8f' % order['rate']))
                table_widget.setItem(i, 6, QtGui.QTableWidgetItem(str(order['orderNumber'])))

                def cancel(ordernr):
                    self._put_task(
                        lambda o=ordernr: self._threadsafe_cancel_order(o),
                        Priorities.Critical)

                if cancel_button:
                    btn = QtGui.QPushButton('X')
                    btn.clicked.connect(
                        lambda chk, v=order['orderNumber']: cancel(v))
                    table_widget.setCellWidget(i, 7, btn)
                i += 1
        table_widget.setSortingEnabled(True)

    def _threadsafe_cancel_order(self, order_nr):
        log.info('cancel order %r', order_nr)
        QtCore.QMetaObject.invokeMethod(
            self, "_handle_order_canceled", QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(dict, self._trader_api.cancel_order(order_nr)),
        )

    @QtCore.pyqtSlot(dict)
    def _handle_order_canceled(self, result):
        log.info('cancel returned %r', result)
        self._balances_dirty = True

    def _add_market(self, market, list_widget):
        if market in self._markets: return
        log.info('add market: %r', market)

        market_widget = MarketWidget(
            self._data.create_trade_history(market), self._trader_api)
        market_widget_item = MarketWidgetItem(market_widget, list_widget)
        market_widget.updated.connect(
            lambda: list_widget.sortItems(QtCore.Qt.DescendingOrder))
        market_widget_item.set_height(self._config['graph_height'])

        market_widget._history_length = self._config['history_length_h'] * 3600
        self._markets[market] = market_widget
        list_widget.setMaximumHeight(
            list_widget.count() * (5 + self._config['graph_height']))


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
    def handle_sigusr1(_, frame) -> None:
        """ interrupt running process, and provide a python prompt for
            interactive debugging.
            see http://stackoverflow.com/questions/132058
               "showing-the-stack-trace-from-a-running-python-application"
        """
        log.info('signal SIGUSR1 received, print stack trace')
        for f in traceback.format_stack(frame):
            for l in f.splitlines():
                log.info(l)

    args = get_args()

    log.basicConfig(
        level=log.DEBUG if args.verbose else log.INFO,
        format='%(asctime)s.%(msecs)03d %(levelname)s %(threadName)s %(message)s',
        datefmt="%y%m%d-%H%M%S")

    log.addLevelName(log.CRITICAL, '(CC)')
    log.addLevelName(log.ERROR,    '(EE)')
    log.addLevelName(log.WARNING,  '(WW)')
    log.addLevelName(log.INFO,     '(II)')
    log.addLevelName(log.DEBUG,    '(DD)')
    log.addLevelName(log.NOTSET,   '(NA)')

    mftl.util.ALLOW_CACHED_VALUES = 'ALLOW' if args.allow_cached else 'NEVER'

    log.info('or run `kill -10 %d` to show stack trace', os.getpid())
    signal.signal(signal.SIGUSR1, handle_sigusr1)

    sys.exit(show_gui())


if __name__ == '__main__':
    main()

