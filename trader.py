#!/usr/bin/env python3

__all__ = ['translate_trade']

import os
try:
    import ujson as json
except ImportError:
    import json
import urllib
import http
from urllib.request import urlopen, Request
from datetime import datetime
from pprint import pprint
import hmac
import hashlib
import socket
import logging as log
import time

ALLOW_CACHED_VALUES = 'ALLOW'  # 'NEVER', 'FORCE'
MOST_RECENTLY = 9999999999

def get_full_name(short):
    try:
        return {
            'BTC':   'BC',
            'USDT':  'USDTether',
            'ETH':   'Ethereum',
            'ETC':   'Eth. Cl.',
            'XMR':   'Monero',
            'LTC':   'Litecoin',
            'BCN':   'Bytecoin',
            'XVC':   'VCASH',
            'BTS':   'Bitshare',
            'NXT':   'Nxt',
            'AMP':   'Synereo',
            'VTC':   'Vertcoin',
            'XRP':   'Ripple',
            'DASH':  'Dash',
            'GNT':   'Golem',
            'FLO':   'Florin',
            'BURST': 'Burst',
            'SC':    'Siacoin',
            'DOGE':  'Dodgecoin',
            'GRC':   'Gridcoin',
            'STRAT': 'Stratis',
            }[short]
    except KeyError:
        return 'unknown(%s)' % short

class ServerError(RuntimeError):
    pass

def ema(data, alpha):
    ''' returns eponential moving average
    '''
    alpha_n = 1 - alpha
    result = []
    n = data[0]
    for x in data:
        n = alpha * x + alpha_n * n
        result.append(n)
    return result


def vema(totals, amounts, a):
    ''' returns the volume weighted eponential moving average
    '''
    smooth_totals = ema(totals, a)
    smooth_amounts = ema(amounts, a)
    return [t / c for t, c in zip(smooth_totals, smooth_amounts)]


class TradeHistory:
    def __init__(self, market, step_size_sec=3600):
        self._market = market
        self._hdata = []
        self._step_size_sec = step_size_sec
        self._update_threshold_sec = 60.
        self._history_max_duration = 24 * 3600

    def load(self):
        try:
            with open('trade_history-%s.json' % self._market) as f:
                self._hdata = json.load(f)
        except FileNotFoundError:
            pass
        except json.JSONDecodeError as exc:
            log.warning(
                'could not load TradeHistory for %r: %r', self._market, exc)

    def save(self):
        with open('trade_history-%s.json' % self._market, 'w') as f:
            json.dump(self._hdata, f)

    def clear(self):
        self._hdata = []

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return 'TradeHistory(%r, duration=%.1f, len=%d)' % (
            self._market, self.get_duration() / 60, len(self._hdata))

    def fetch_next(self):
        current_time = time.time()
        log.info('update trade history for %r after %d seconds',
                 self._market, current_time - self.last_time())

        if current_time - self.last_time() > 6 * 3600:
            # last update too long ago to fill the gap (for now)
            self.clear()

        if not self._hdata:
            log.debug('fetch_next: there is no data yet - fetch an hour')
            start = current_time - self._step_size_sec
            end = MOST_RECENTLY
        elif current_time - self.last_time() > self._update_threshold_sec:
            log.debug('fetch_next: more than a couple of seconds have passed '
                      'since last update - do an update now')
            start = self.last_time()
            end = MOST_RECENTLY
        elif current_time - self.first_time() < self._history_max_duration:
            log.debug("fetch_next: we don't need to update recent parts of the "
                      "graph - fetch older data instead.")
            start = self.first_time() - self._step_size_sec
            end = self.first_time()
        else:
            log.debug("fetch_next: no need to update anything - just exit")
            return

        self._attach_data(Api.get_trade_history(
            *self._market.split('_'), start, end))

    def count(self):
        return len(self._hdata)

    def data(self):
        return self._hdata

    def first_time(self):
        if not self._hdata: return 0.
        return self._hdata[0]['time']

    def last_rate(self):
        if not self._hdata: return 0.
        return self._hdata[-1]['total'] / self._hdata[-1]['amount']

    def last_time(self):
        if not self._hdata: return 0.
        return self._hdata[-1]['time']

    def get_duration(self):
        return self.last_time() - self.first_time()

    def _attach_data(self, data):
        if not data:
            log.warning('_attach_data tries to handle an empy list')
            return
        if not self._hdata:
            self._hdata = data
            return

        # check contiguousity
        # good:    [......(.].....)
        # bad:     [......].(.....)
        # bad too: [......](......)
        if (data[0]['time'] > self._hdata[-1]['time'] or
            self._hdata[0]['time'] > data[-1]['time']):
            raise ValueError('lists are discontiguous')

        # check merge contains new data
        # bad: [..(..)..]
        assert (data[0]['time'] <= self._hdata[0]['time'] or
                data[-1]['time'] >= self._hdata[-1]['time'])

        def merge(list1, list2):
            def find(lst, key, value):
                for i, dic in enumerate(lst):
                    if dic[key] == value:
                        return i
                return -1
            return (list1[:find(list1, 'globalTradeID',
                                list2[0]['globalTradeID'])] +
                    list2)

        self._hdata = (merge(data, self._hdata)
                       if data[0]['time'] < self._hdata[0]['time'] else
                       merge(self._hdata, data))

    def get_plot_data(self, ema_factor=0.005):
        totals = [e['total'] for e in self._hdata]
        amounts = [e['amount'] for e in self._hdata]
        times = [e['time'] for e in self._hdata]
        rates_vema = vema(totals, amounts, ema_factor)
        return times[50:], rates_vema[50:]



def get_plot_data(data, ema_factor):
    totals = [e['total'] for e in data]
    amounts = [e['amount'] for e in data]
    times = [time.mktime(e['date'].timetuple()) - time.time() for e in data]

    rates_vema = vema(totals, amounts, ema_factor)

    return times, rates_vema


def get_unique_name(data: dict) -> str:
    ''' turn dict into unambiguous string '''
    return ('.'.join('%s=%s' % (k, 'xxx' if k in {'start', 'nonce'} else v)
                      for k, v in sorted(data.items()))
            .replace(',', '_')
            .replace('/', '_')
            .translate(dict.fromkeys(map(ord, u"\"'[]{}() "))))


def translate_trade(trade):
    date = datetime.strptime(trade['date'], '%Y-%m-%d %H:%M:%S')
    return {#'date': date,
            'time': time.mktime(date.timetuple()) - time.altzone,
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


def _fetch_http(request, request_data):
    assert ALLOW_CACHED_VALUES in {'NEVER', 'ALLOW', 'FORCE'}
    log.debug('caching policy: %r', ALLOW_CACHED_VALUES)
    log.debug('XXXX fetch %r', request_data)
    os.makedirs('cache', exist_ok=True)
    filename = os.path.join('cache', get_unique_name(request_data) + '.cache')
    if ALLOW_CACHED_VALUES in {'NEVER', 'ALLOW'}:
        try:
            while True:
                try:
                    time.sleep(0.5)
                    #t1 = time.time()
                    result = urlopen(request, timeout=15).read()
                    #log.info('fetched in %6.2fs: %r', time.time() - t1, request_data)
                    break
                except http.client.IncompleteRead as exc:
                    log.warning('exception caught in urlopen: %r - retry', exc)
                except socket.timeout as exc:
                    log.warning('socket timeout - retry')

            with open(filename, 'wb') as file:
                file.write(result)
            return result.decode()
        except urllib.error.URLError as exc:
            if ALLOW_CACHED_VALUES == 'NEVER':
                raise ServerError(repr(exc)) from exc
    try:
        with open(filename, 'rb') as file:
            log.warning('use chached values for %r', request)
            return file.read().decode()
    except FileNotFoundError as exc:
        raise ServerError(repr(exc)) from exc


class Api:
    def __init__(self, key, secret):
        self._key = key.encode()
        self._secret = secret.encode()
        self._coins = None
        self._markets = None

    def _run_private_command(self, command, req=None):
        request_data = {**(req if req else {}),
                        **{'command': command,
                           'nonce': int(time.time() * 1000)}}
        post_data = urllib.parse.urlencode(request_data).encode()
        sign = hmac.new(
            self._secret,
            msg=post_data,
            digestmod=hashlib.sha512).hexdigest()
        request = Request(
            'https://poloniex.com/tradingApi',
            data=post_data,
            headers={'Sign': sign, 'Key': self._key})
        result = json.loads(_fetch_http(request, request_data))
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    @staticmethod
    def _run_public_command(command: str, req=None) -> str:
        request_data = {**(req if req else {}),
                        **{'command': command}}
        post_data = '&'.join(['%s=%s' % (k, v) for k, v in request_data.items()])
        request = 'https://poloniex.com/public?' + post_data
        result = json.loads(_fetch_http(request, request_data))
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    @staticmethod
    def _get_trade_history(currency_pair, start=None, stop=None) -> dict:
        req = {'currencyPair': currency_pair}
        if start:
            req.update({'start': start if stop else time.time() - start,
                        'end': stop if stop else MOST_RECENTLY})
        return list(reversed([translate_trade(t)
                for t in Api._run_public_command(
                    'returnTradeHistory', req)]))

    @staticmethod
    def get_trade_history(primary, coin, start, stop=None) -> dict:
        if primary == coin:
            return []
        return Api._get_trade_history(primary + '_' + coin, start, stop)

    @staticmethod
    def get_current_rate(market):
        total, amount, minr, maxr = sum_trades(Api._get_trade_history(market))
        return total / amount, minr, maxr

    @staticmethod
    def get_ticker() -> dict:
        return {c: translate_ticker(v)
                for c, v in Api._run_public_command('returnTicker').items()}

    def get_balances(self) -> dict:
        return {c: float(v)
                for c, v in self._run_private_command('returnBalances').items()
                if float(v) > 0.0}

    def get_complete_balances(self) -> dict:
        return {c: {k: float(a) for k, a in v.items()}
                for c, v in self._run_private_command(
                    'returnCompleteBalances').items()}

    def cancel_order(self, order_nr) -> dict:
        return self._run_private_command(
            'cancelOrder', {'orderNumber': order_nr})

    def get_open_orders(self) -> dict:
        return {c: o
                for c, o in self._run_private_command(
                    'returnOpenOrders', {'currencyPair': 'all'}).items()
                if o}

    def get_order_history(self) -> dict:
        return self._run_private_command(
            'returnTradeHistory', {'currencyPair': 'all',
                                   'start': 0,
                                   'end': MOST_RECENTLY})

    @staticmethod
    def extract_coin_data(ticker):
        coins = {}
        for m in ticker:
            c1, c2 = m.split('_')
            if not c1 in coins: coins[c1] = set()
            coins[c1].add(c2)
        return coins

    def get_coins(self, refetch=False):
        ''' returns
        '''
        if refetch or not self._coins:
            ticker = self.get_ticker()
            self._coins = self.extract_coin_data(ticker)
            self._markets = ticker.keys()
        return self._coins

    def get_markets(self, refetch=False):
        if refetch or not self._markets:
            ticker = self.get_ticker()
            self._coins = self.extract_coin_data(ticker)
            self._markets = ticker.keys()
        return self._markets

    def check_order(self, *,
                    sell: tuple, buy: str,
                    suggestion_factor: float) -> float:
        amount, what_to_sell = sell
        log.info('try to sell %f %r for %r', amount, what_to_sell, buy)# todo: correct

        def check_balance():
            balances = self.get_balances()
            if not what_to_sell in balances:
                raise ValueError(
                    'You do not have %r to sell' % what_to_sell)
            log.info('> you have %f %r', balances[what_to_sell], what_to_sell)
            if balances[what_to_sell] < amount:
                raise ValueError(
                    'You do not have enough %r to sell (just %f)' % (
                        what_to_sell, balances[what_to_sell]))

        check_balance()  # todo: cached balance?
        if (what_to_sell in self.get_coins() and
                buy in self.get_coins()[what_to_sell]):
            market = what_to_sell + '_' + buy
            action = 'buy'
        elif (buy in self.get_coins() and
                  what_to_sell in self.get_coins()[buy]):
            market = buy + '_' + what_to_sell
            action = 'sell'
        else:
            raise ValueError(
                'No market available for %r -> %r' % (
                    what_to_sell, buy))

        # [todo]: make sure this is correct!!!
        current_rate, minr, maxr = self.get_current_rate(market)

        target_rate = (
            current_rate * suggestion_factor if action == 'buy' else
            current_rate / suggestion_factor)

        log.info('> current rate is %f(%f..%f), target is %f',
                 current_rate, minr, maxr, target_rate)

        return {'market': market,
                'action': action,
                'rate': target_rate,
                'amount': (amount if action == 'sell' else
                           amount / target_rate)}

    def place_order(self, *,
                    market: str,
                    action: str,
                    rate: float,
                    amount: float) -> dict:
        assert action in {'buy', 'sell'}
        log.info('place order: %r %r %f %f', market, action, rate, amount)
        return self._run_private_command(
            action,
            {'currencyPair': market,
             'rate': rate,
             'amount': amount})


def get_price(ticker, currency, coin):
    return 1.0 if currency == coin else ticker['%s_%s' % (currency, coin)]['last']


def get_EUR():
    def get_bla():
        return json.loads(_fetch_http(
            'https://api.fixer.io/latest', {'url':'api.fixer.io/latest'}))
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
    pprint(api.get_order_history())


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

