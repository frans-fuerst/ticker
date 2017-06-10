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
import json
import logging as log
from PyQt4 import QtGui, QtCore, Qt, uic
import qwt
import yappi

import trader

def toggle_profiling(clock_type: str='wall') -> None:
    # https://code.google.com/archive/p/yappi/wikis/usageyappi.wiki
    # https://code.google.com/archive/p/yappi/wikis/UsageYappi_v092.wiki
    if not yappi.is_running():
        yappi.set_clock_type(clock_type)
        yappi.start(builtins=False)
        yappi.profile_begin_time = yappi.get_clock_time()
        yappi.profile_begin_wall_time = time.time()
        print(
            "now capturing profiling info of with clock_type='%s'" %
            yappi.get_clock_type())
    else:
        yappi.stop()
        func_stats = yappi.get_func_stats()
        thread_stats = yappi.get_thread_stats()
        time_yappi = yappi.get_clock_time()
        duration_yappi = time_yappi - yappi.profile_begin_time
        time_wall = time.time()
        duration_wall = time_wall - yappi.profile_begin_wall_time

        yappi.clear_stats()

        print('Profiling time: %s - %s = %.1fs\n' % (
            time.asctime(time.localtime(yappi.profile_begin_wall_time)),
            time.asctime(time.localtime(time_wall)),
            duration_wall,
        ))
        print('yappi duration: %.1fs\n' % duration_yappi)

        func_stats.print_all(
            out=out,
            columns={0: ("name",  40),
                     1: ("ncall",  5),
                     2: ("tsub",   8),
                     3: ("ttot",   8),
                     4: ("tavg",   8)})
        thread_stats.print_all(
            out=out,
            columns={0: ("name", 23),
                     1: ("id",    5),
                     2: ("tid",  15),
                     3: ("ttot",  8),
                     4: ("scnt", 10)})

class DataPlot(qwt.QwtPlot):

    def __init__(self, *args):
        qwt.QwtPlot.__init__(self, *args)

        #self.setCanvasBackground(Qt.Qt.green)
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
        self._history_length = 100
        self._marker_value = None
        self.layout().addWidget(self._plot)

    def threadsafe_update_plot(self):
        log.info('update trade history for %r', self._market)
        data = trader.Api.get_trade_history(
            *self._market.split('_'),
            start=self._history_length)
        if not data: return
        times, rates = trader.get_plot_data(data, 0.995)
        QtCore.QMetaObject.invokeMethod(
            self, "_set_data",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(list, times),
            QtCore.Q_ARG(list, rates))
        log.info('done')

    @QtCore.pyqtSlot(list, list)
    def _set_data(self, times, rates):
        self._current_rate = rates[-1]
        self.lbl_current.setText('%.2fh / %f' % (
            (times[-1] - times[0]) / 3600, self._current_rate))
        self._plot.set_data(times, rates)
        mins, maxs = min(rates), max(rates)
        if self._marker_value:
            maxs = max(maxs, self._marker_value)
            mins = min(mins, self._marker_value)
        self._plot.setAxisScale(qwt.QwtPlot.yLeft, min(mins, maxs * 0.9), maxs)
        self.redraw()

    def redraw(self):
        self._plot.redraw()

    def set_marker(self, value):
        self._marker_value = value
        self._plot.set_marker(self._marker_value)

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
        self._config = {'graph_height':   140,
                        'history_length_h': 4,
                        'update_interval_sec': 180,
                        'suggested_rate_factor': 1.0,
                        'markets': (
                            'BTC_ETC', # 'Ethereum Classic
                            'BTC_XMR', #'Monero
                        )}
        try:
            self._config.update(ast.literal_eval(open('config').read()))
        except FileNotFoundError:
            log.warning("you don't have a 'config' file, use default values")

        try:
            self._trader_api = trader.Api(**ast.literal_eval(open('k').read()))
            log.info('initialize personal balances..')
        except FileNotFoundError:
            log.warning('did not find key file - only public access is possible')
            self._trader_api = None

        def check_new_markets():
            current_markets = set(trader.Api.get_ticker().keys())
            try:
                last_markets = set(json.loads(open('last_markets').read()))
            except FileNotFoundError:
                last_markets = set()
            if current_markets - last_markets:
                if QtGui.QMessageBox.question(
                        self, 'New Markets!!!11!!',
                        "Be sure to buy coins of %r\n\nSave markets?" % (
                            current_markets - last_markets),
                        QtGui.QMessageBox.Ok, QtGui.QMessageBox.No
                        ) == QtGui.QMessageBox.Ok:
                    open('last_markets', 'w').write(json.dumps(list(current_markets)))

        check_new_markets()

        self._balances = self._fetch_balances()
        self._markets = {}
        self._last_update = None

        update_timer = QtCore.QTimer(self)
        update_timer.timeout.connect(self._update_timer_timeout)
        update_timer.setInterval(self._config['update_interval_sec'] * 1000)
        update_timer.start()

        time_info_timer = QtCore.QTimer(self)
        time_info_timer.timeout.connect(self._time_info_timer_timeout)
        time_info_timer.setInterval(1000)
        time_info_timer.start()

        self._worker_thread = threading.Thread(target=self._worker_thread_fn)
        self._tasks = queue.Queue()
        self._worker_thread.start()

        self.pb_check.clicked.connect(self._pb_check_clicked)
        self.pb_place_order.clicked.connect(self._pb_place_order_clicked)
        self.pb_refresh.clicked.connect(self._pb_refresh_clicked)
        self.cb_trade_curr_sell.currentIndexChanged.connect(self._cb_trade_curr_sell_currentIndexChanged)
        self.cb_trade_curr_buy.currentIndexChanged.connect(self._cb_trade_curr_buy_currentIndexChanged)
        self.le_trade_amount.textChanged.connect(self._le_trade_amount_textChanged)

        # sort by time
        self.tbl_order_history.sortItems(0, QtCore.Qt.DescendingOrder)
        # sort by EUR value
        self.tbl_balances.sortItems(4, QtCore.Qt.DescendingOrder)
        self.tbl_open_orders.sortItems(2, QtCore.Qt.DescendingOrder)
        self.le_suggested_rate_factor.setText(str(self._config['suggested_rate_factor']))

        self._add_market('USDT_BTC')
        for m in self._config['markets']:
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
        log.info('got close event, wait for worker to finish..')
        self._tasks.put(None)
        self._worker_thread.join()
        log.info('bye bye!')

    def _worker_thread_fn(self):
        while True:
            f = self._tasks.get()
            if f is None:
                log.info('exit _worker_thread_fn()')
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

    def _pb_refresh_clicked(self):
        self._update_values()

    def _pb_check_clicked(self):
        self.pb_place_order.setEnabled(False)
        sell = (float(self.le_trade_amount.text()),
                self.cb_trade_curr_sell.currentText())
        buy = self.cb_trade_curr_buy.currentText()
        speed_factor = float(self.le_suggested_rate_factor.text())
        log.info('create order from: sell=%r buy=%r speed_factor=%f',
                 sell, buy, speed_factor)
        try:
            order = self._trader_api.check_order(
                sell=sell, buy=buy,
                suggestion_factor=speed_factor)
        except (RuntimeError, ValueError) as exc:
            log.error('cannot place order: %s', exc)

        self.le_order_market.setText(order['market'])
        self.le_order_amount.setText(str(order['amount']))
        self.le_order_rate.setText(str(order['rate']))
        self.cb_order_action.setCurrentIndex(
            self.cb_order_action.findText(order['action']))
        self.pb_place_order.setEnabled(True)

    def _pb_place_order_clicked(self):
        def save_order(order):
            if not order: return
            try:
                orders = json.loads(open('orders').read())
            except FileNotFoundError:
                orders = []
            orders.append(result)
            open('orders', 'w').write(json.dumps(orders))

        order = {'market': self.le_order_market.text(),
                 'action': self.cb_order_action.currentText(),
                 'rate': float(self.le_order_rate.text()),
                 'amount': float(self.le_order_amount.text())}

        log.info('place order: %r', order)

        speed_factor = float(self.le_suggested_rate_factor.text())

        try:
            result = self._trader_api.place_order(**order)
            result.update({'speed_factor': speed_factor,
                           'time': time.time()})
            save_order(result)
        except (RuntimeError, ValueError) as exc:
            log.error('cannot place order: %s', exc)

        try:
            self._threadsafe_update_balances()
        except trader.ServerError as exc:
            log.error('cannot place order: %s', exc)

    def _le_trade_amount_textChanged(self):
        self.pb_place_order.setEnabled(False)

    def _cb_trade_curr_sell_currentIndexChanged(self, index):
        #self.pb_place_order.setEnabled(False)
        selected = self.cb_trade_curr_sell.itemText(index)
        if not selected: return
        log.info('selected currency to sell: %r', selected)
        self.le_trade_amount.setText(str(self._balances[selected]))

    def _cb_trade_curr_buy_currentIndexChanged(self, index):
        #self.pb_place_order.setEnabled(False)
        selected = self.cb_trade_curr_buy.itemText(index)
        if not selected: return

    def _threadsafe_update_balances(self):
        if not self._trader_api: return
        log.info("update balances..")
        balances = self._trader_api.get_balances()
        eur_price = trader.get_EUR()
        orders = self._trader_api.get_open_orders()
        order_history = self._trader_api.get_order_history()
        QtCore.QMetaObject.invokeMethod(
            self, "_set_balance_data",
            QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(dict, balances),
            QtCore.Q_ARG(float, eur_price),
            QtCore.Q_ARG(dict, orders),
            QtCore.Q_ARG(dict, order_history),
        )

    @QtCore.pyqtSlot(dict, float, dict, dict)
    def _set_balance_data(self, balances, eur_price, orders, order_history):
        self._balances = balances
        self.cb_trade_curr_sell.clear()
        self.cb_trade_curr_buy.clear()

        self.tbl_balances.setSortingEnabled(False)
        self.tbl_balances.setRowCount(len(self._balances))

        xbt_usd_rate = self._markets['USDT_BTC'].current_rate()
        btc_total = 0.
        eur_total = 0.
        i = 0
        for c, a in self._balances.items():
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
            self.tbl_balances.setItem(i, 0, QtGui.QTableWidgetItem('%s' % c))
            self.tbl_balances.setItem(i, 1, QtGui.QTableWidgetItem('%10.5f' % a))
            self.tbl_balances.setItem(i, 2, QtGui.QTableWidgetItem('%10.5f' % _btc_rate))
            self.tbl_balances.setItem(i, 3, QtGui.QTableWidgetItem('%10.5f' % _add_btc))
            self.tbl_balances.setItem(i, 4, QtGui.QTableWidgetItem('%10.5f' % _add_eur))
            i += 1
        self.tbl_balances.setSortingEnabled(True)

        self.cb_trade_curr_buy.addItem('BTC')
        for c in sorted(self._trader_api.get_markets()['BTC']):
            self.cb_trade_curr_buy.addItem(c)

        if not 'USDT_BTC' in self._markets: return

        self.lbl_XBT_USD.setText('%.2f' % xbt_usd_rate)
        self.lbl_XBT_EUR.setText('%.2f' % (xbt_usd_rate * eur_price))
        self.lbl_bal_BTC.setText('%.4f' % (btc_total))
        self.lbl_bal_EUR.setText('%.4f' % (eur_total))

        self._fill_order_table(self.tbl_open_orders, orders, cancel_button=True)
        self._fill_order_table(self.tbl_order_history, order_history)
        for m, history in order_history.items():
            for h in history:
                if h['type'] == 'buy' and m in self._markets:
                    print(m,  float(h['total']) / float(h['amount']))
                    self._markets[m].set_marker(
                        float(h['total']) / float(h['amount']))
                    self._markets[m].redraw()
                    break

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
                table_widget.setItem(i, 3, QtGui.QTableWidgetItem(order['amount']))
                table_widget.setItem(i, 4, QtGui.QTableWidgetItem(order['total']))
                table_widget.setItem(i, 5, QtGui.QTableWidgetItem(order['rate']))
                table_widget.setItem(i, 6, QtGui.QTableWidgetItem(order['orderNumber']))
                on = order['orderNumber']
                if cancel_button:
                    btn = QtGui.QPushButton('X')
                    btn.clicked.connect(
                        lambda: self._cancel_order(on))
                    table_widget.setCellWidget(i, 7, btn)
                i += 1
        table_widget.setSortingEnabled(True)
        for i in range(table_widget.columnCount()):
            table_widget.horizontalHeader().setResizeMode(
                i, QtGui.QHeaderView.ResizeToContents)


    def _cancel_order(self, order_nr):
        try:
            log.info('cancel order %r', order_nr)
            result = self._trader_api.cancel_order(order_nr)
            self._threadsafe_update_balances()
            log.info('result: %r', result)
        except Exception as exc:
            log.error('Exception while cancelling: %r', exc)

    def _add_market(self, market):
        if market in self._markets: return
        log.info('add market: %r', market)
        new_item = QtGui.QListWidgetItem()
        new_item.setSizeHint(QtCore.QSize(110, self._config['graph_height']))
        new_item.setFlags(QtCore.Qt.ItemIsEnabled)
        new_market = MarketWidget(market, self._trader_api)
        self.lst_markets.addItem(new_item)
        self.lst_markets.setItemWidget(new_item, new_market)
        new_market._history_length = self._config['history_length_h'] * 3600
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
    def handle_sigusr1(signal: int, frame) -> None:
        """ interrupt running process, and provide a python prompt for
            interactive debugging.
            see http://stackoverflow.com/questions/132058
               "showing-the-stack-trace-from-a-running-python-application"
        """
        import traceback
        log.info('signal SIGUSR1 received, print stack trace')
        for f in traceback.format_stack(frame):
            for l in f.splitlines():
                log.info(l)

    args = get_args()

    log.basicConfig(level=log.INFO)

    trader.ALLOW_CACHED_VALUES = 'ALLOW' if args.allow_cached else 'NEVER'

    log.info('or run `kill -10 %d` to show stack trace', os.getpid())
    signal.signal(signal.SIGUSR1, handle_sigusr1)

    sys.exit(show_gui())


if __name__ == '__main__':
    main()

