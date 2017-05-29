#!/usr/bin/env python3

import json
import urllib
import sys
import os
from urllib.request import urlopen, Request
from datetime import datetime
from pprint import pprint
from ast import literal_eval
import hmac
import hashlib
import logging
import time
import argparse

PUBLIC_URL = 'https://poloniex.com/public?command=%s'
BASE = {'BTC', 'ETH', 'XMR', 'USDT'}


def translate_trade(trade):
    return {'date': datetime.strptime(trade['date'], '%Y-%m-%d %H:%M:%S'),
            'tradeID': trade['tradeID'],
            'globalTradeID': trade['globalTradeID'],
            'total': float(trade['total']),
            'amount': float(trade['amount']),
            'rate': float(trade['rate']),
            'type': trade['type']}

def translate_ticker(val):
    return {'baseVolume': float(val['baseVolume']),
            'high24hr': float(val['high24hr']),
            'highestBid': float(val['highestBid']),
            'id': val['id'],
            'isFrozen': val['id'] != '0',
            'last': float(val['last']),
            'low24hr': float(val['low24hr']),
            'lowestAsk': float(val['lowestAsk']),
            'percentChange': float(val['percentChange']),
            'quoteVolume': float(val['quoteVolume'])}

class Api:
    def __init__(self, key, secret):
        self._key = key.encode()
        self._secret = secret.encode()
        self._markets = self._get_markets()

    def _run_private_command(self, command, req=None):
        req = req if req else {}
        req.update({
            'command': command,
            'nonce': int(time.time() * 1000)})
        post_data = urllib.parse.urlencode(req).encode()
        sign = hmac.new(
            self._secret,
            msg=post_data,
            digestmod=hashlib.sha512).hexdigest()
        ret = urlopen(Request(
            'https://poloniex.com/tradingApi',
            data=post_data,
            headers={'Sign': sign, 'Key': self._key})).read()
        return json.loads(ret.decode())

    def _run_public_command(self, command: str, req=None) -> str:
        req = {**(req if req else {}), **{'command': command}}
        post_data = '&'.join(['%s=%s' % (k, v) for k, v in req.items()])
        url = 'https://poloniex.com/public?'
        ret = urlopen(url + post_data).read()
        return json.loads(ret.decode())

    def _get_trade_history(self, currency_pair, duration=None) -> dict:
        req = {'currencyPair': currency_pair}
        if duration:
            req.update({'start': '%d' % (time.time() - duration),
                        'end': '9999999999'})
        return [translate_trade(t)
                for t in self._run_public_command(
                    'returnTradeHistory', req)]

    def get_trade_history(self, primary, coin, duration) -> dict:
        if primary == coin:
            return []
        return self._get_trade_history(primary + '_' + coin, duration)

    def get_current_rate(self, market):
        total, amount, minr, maxr = sum_trades(self._get_trade_history(market))
        return total / amount, minr, maxr

    def get_ticker(self) -> dict:
        return {c: translate_ticker(v)
                for c, v in self._run_public_command('returnTicker').items()}

    def get_balances(self) -> dict:
        return {c: float(v)
                for c, v in self._run_private_command('returnBalances').items()
                if float(v) > 0.0}

    def get_complete_balances(self) -> dict:
        return {c: {k: float(a) for k, a in v.items()}
                for c, v in self._run_private_command('returnCompleteBalances').items()}

    def get_open_orders(self) -> dict:
        return {c: o
                for c, o in self._run_private_command('returnOpenOrders', {'currencyPair': 'all'}).items()
                if o}

    def _get_markets(self):
        markets = {}
        for m in self.get_ticker():
            c1, c2 = m.split('_')
            if not c1 in markets: markets[c1] = set()
            markets[c1].add(c2)
        return markets

    def place_order(self, *, sell: tuple, buy: str, fire=False):
        amount, what_to_sell = sell
        print('try to sell %f %r for %r' % (amount, what_to_sell, buy))

        def check_balance():
            balances = self.get_balances()
            if not what_to_sell in balances:
                raise ValueError(
                    'You do not have %r to sell' % what_to_sell)
            print('> you have %f %r' % (balances[what_to_sell], what_to_sell))
            if balances[what_to_sell] < amount:
                raise ValueError(
                    'You do not have enough %r to sell (just %f)' % (
                        what_to_sell, balances[what_to_sell]))

        check_balance()
        if (what_to_sell in self._markets and
                buy in self._markets[what_to_sell]):
            market = what_to_sell + '_' + buy
            action = 'buy'
        elif (buy in self._markets and
                  what_to_sell in self._markets[buy]):
            market = buy + '_' + what_to_sell
            action = 'sell'
        else:
            raise ValueError(
                'No market available for %r -> %r' % (
                    what_to_sell, buy))
        current_rate, minr, maxr = self.get_current_rate(market)
        # [todo]: here we can raise/lower by about 0.5%
        target_rate = current_rate
        target_amount = amount if action == 'sell' else amount / target_rate

        print('> current rate is %f(%f-%f), target is %f' % (
            current_rate, minr, maxr, target_rate))
        print('> %r currencyPair=%s, rate=%f, amount=%f' % (
            action, market, target_rate, target_amount))
        if fire:
            print('> send trade command..')
            pprint(self._run_private_command(
                action,
                {'currencyPair': market,
                 'rate': target_rate,
                 'amount': target_amount}))


def get_price(ticker, currency, coin):
    return 1.0 if currency == coin else ticker['%s_%s' % (currency, coin)]['last']


def get_EUR():
    def get_bla():
        return json.loads(urlopen('http://api.fixer.io/latest').read().decode())
    return 1.0 / float(get_bla()['rates']['USD'])


def get_detailed_balances(api):

    print('get balances..')
    b = api.get_balances()
    print('get ticker..')
    t = api.get_ticker()
    print('get rates..')
    eur_price = get_EUR()
    print('get bitcoin price..')
    xbt_price = get_price(t, 'USDT', 'BTC')

    print('BTC price is USD %.2f / EUR %.2f' % (xbt_price, xbt_price * eur_price))

    hours = 2

    cash_usd = 0.0
    for c, v in sorted(b.items()):
        price = get_price(t, 'BTC', c)
        tot_usd = price * v * xbt_price
        cash_usd += tot_usd
        th = trade_history_digest(
            api.get_trade_history('BTC', c, 60 * 60 * hours))
        print('%r: a=%.5f, p=%.5f(last=%.5f), v=~EUR %6.2f, t=%+6.2f%% (%dh)' % (
            c, v, th['rate'], price, tot_usd * eur_price, th['trend'], hours))

    print('USD %.2f / EUR %.2f' % (cash_usd, cash_usd * eur_price))
    pprint(api.get_open_orders())


def sum_trades(history: list) -> tuple:
    total = 0.0
    amount = 0.0
    min_rate = +99999999
    max_rate = -99999999
    for t in history:
        total += t['total']
        amount += t['amount']
        min_rate = min(min_rate, t['rate'])
        max_rate = max(max_rate, t['rate'])
    return total, amount, min_rate, max_rate


def trade_history_digest(history, calculate_trend=True):
    if not history:
        return {'rate': 1.0,
                'amount': 0.0,
                'total': 0.0,
                'duration': 0,
                'trend': 0.0}
    #pprint(history)
    trend = ((trade_history_digest(history[:len(history) // 2], calculate_trend=False)['rate'] /
              trade_history_digest(history[len(history) // 2:], calculate_trend=False)['rate'] - 1.0 )
             if calculate_trend else 1.0)
    #print(history[0]['date'], "|", history[-1]['date'], "|", len(history), "|", total / amount)
    total, amount, _, _ = sum_trades(history)
    return {'rate': total / amount,
            'amount': amount,
            'total': total,
            'duration': int((history[0]['date'] - history[-1]['date']).total_seconds()),
            'trend': trend * 100,
            }


def get_args() -> dict:
    parser = argparse.ArgumentParser(description='ticker')

    parser.add_argument("-v", "--verbose", action='store_true')
    parser.add_argument('cmd')
    parser.add_argument('arg1', nargs='?')
    parser.add_argument('arg2', nargs='?')
    parser.add_argument('arg3', nargs='?')
    parser.add_argument('arg4', nargs='?')
    return parser.parse_args()


from PyQt4 import QtGui, QtCore, Qt, uic
import qwt
import signal

class Trader(QtGui.QMainWindow):

    def __init__(self):

        class graph:
            def __init__(self, plot, title):
                self._plot = plot
                self._plot.setMaximumHeight(100)
                #self._plot.setCanvasBackground(Qt.black)
                self._plot.setAxisTitle(Qwt.QwtPlot.xBottom, 'Time')
                #self._plot.setAxisScale(Qwt.QwtPlot.xBottom, 0, 10, 1)
                self._plot.setAxisTitle(Qwt.QwtPlot.yLeft, title)
                #self._plot.setAxisScale(Qwt.QwtPlot.yLeft, 0, 250, 40)
                #self._plot.setAxisAutoScale(Qwt.QwtPlot.yLeft, True)
                #self._plot.setAxisAutoScale(Qwt.QwtPlot.xBottom, True)
                self._plot.replot()
                self._plot.enableAxis(Qwt.QwtPlot.xBottom, False)
                #self._plot.enableAxis(Qwt.QwtPlot.yLeft, False)

                self._xdata = []
                self._ydata = []
                self._curve = Qwt.QwtPlotCurve('')
                self._curve.setRenderHint(Qwt.QwtPlotItem.RenderAntialiased)
                #pen = QPen(QColor('limegreen'))
                #pen.setWidth(2)
                #self._curve.setPen(pen)
                #self._curve.setData(self._xdata, self._ydata)

                scaleWidget = plot.axisWidget(Qwt.QwtPlot.yLeft)
                #scaleWidget.setFixedWidth(200)
                #d = scaleWidget.scaleDraw()
                #d.minimumExtent
                scaleWidget.scaleDraw().setMinimumExtent(100)

                self._curve.attach(self._plot)

            def add_value(self, t, value):
                if len(self._ydata) > 0 and self._ydata[-1] == value:
                    return
                self._xdata.append(t)
                self._ydata.append(value)
                self._curve.setData(self._xdata, self._ydata)
                #self.plt_raw.setAxisScale(Qwt.QwtPlot.xBottom, self._xdata[0], self._xdata[-1])
                #self.plt_raw.setAxisScale(Qwt.QwtPlot.xBottom, self._xdata[0], self._xdata[-1])
                self._plot.replot()


        self._colors = [
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

        QtGui.QMainWindow.__init__(self)

        self.setMouseTracking(True)
        self._directory = os.path.dirname(os.path.realpath(__file__))
        uic.loadUi(os.path.join(self._directory, 'trader.ui'), self)

        #self._graphs = {}
        #self._graphs['raw']        = graph(self.plt_raw, 'raw data')
        #self._graphs['meditation'] = graph(self.plt_meditation, 'meditation')
        #self._graphs['attention']  = graph(self.plt_attention, 'attention')
        #self._graphs['delta']      = graph(self.plt_delta, 'delta')
        #self._graphs['theta']      = graph(self.plt_theta, 'theta')
        #self._graphs['low_alpha']  = graph(self.plt_low_alpha, 'alpha_low')
        #self._graphs['high_alpha'] = graph(self.plt_high_alpha, 'alpha_high')
        #self._graphs['low_beta']   = graph(self.plt_low_beta, 'beta_low')
        #self._graphs['high_beta']  = graph(self.plt_high_beta, 'beta_high')
        #self._graphs['low_gamma']  = graph(self.plt_low_gamma, 'gamma_low')
        #self._graphs['mid_gamma']  = graph(self.plt_high_gamma, 'gamma_mid')
        #self.plt_raw.enableAxis(Qwt.QwtPlot.xBottom, True)
        #self.plt_raw.setMaximumHeight(200)

        self.show()

def show_gui():
#    logging.basicConfig(level=logging.INFO)

#    LOG.info(sys.executable)
#    LOG.info('.'.join((str(e) for e in sys.version_info)))

    app = QtGui.QApplication(sys.argv)
    ex = Trader()
    signal.signal(signal.SIGINT, signal.SIG_DFL)
#    for s in (signal.SIGABRT, signal.SIGINT, signal.SIGSEGV, signal.SIGTERM):
#        signal.signal(s, lambda signal, frame: sigint_handler(signal, ex))

    # catch the interpreter every now and then to be able to catch signals
#    timer = QtCore.QTimer()
#    timer.start(200)
#    timer.timeout.connect(lambda: None)

    sys.exit(app.exec_())


def main():
    args = get_args()
    api = Api(**literal_eval(open('k').read()))

    if args.cmd == 'bal':
        get_detailed_balances(api)
    elif args.cmd == 'bla':
        t = api.get_ticker()
        for c, v in sorted(t.items(), key=lambda x: x[1]['percentChange'], reverse=True)[:5]:
            print(c, v['percentChange'])
    elif args.cmd == 'best':
        print('get balances..')
        for c, v in api.get_balances().items():
            print(c, v)
            print(trade_history_digest(api.get_trade_history('BTC', c, 60 * 60 * 2)))
    elif args.cmd == 'trade':
        api.place_order(sell=(float(args.arg1), args.arg2), buy=args.arg3, fire=args.arg4=='fire')
        print('your orders:', api.get_open_orders())
    elif args.cmd == 'gui':
        show_gui()
    else:
        #api.place_order(sell=(0.001, 'BTC'), buy='FLO', fire=True)
        #api.place_order(sell=(3, 'XMR'), buy='BTC')
        #api.place_order(sell=(0.004, 'BTC'), buy='XMR')
        pass

#    pprint(t)
#    pprint(t.keys())
#    pprint(len(t))
#    for k in t:
#        h = get_trade_history(api, k)

    #pprint(get_trade_history(api, 'USDT_BTC'))
    # pprint(t)
    #pprint()
    #pprint(get_USDT_value(t, 'XMR'))
    #pprint(get_USDT_value(t, 'BTC'))


if __name__ == '__main__':
    main()

