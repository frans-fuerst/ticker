#!/usr/bin/env python3

# pylint: disable=missing-docstring
# pylint: disable=invalid-name
# Disable the next check to allow fixtures.
# pylint: disable=redefined-outer-name
import os, sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
import trader

from pprint import pprint
import pytest

#class myfix:
    #def __enter__(self, *args):
        #print('enter')
        #return self
    #def __exit__(self):
        #print('exit')
    #def out(self, m):
        #print(m)


#@pytest.fixture(scope="module")
#def mod_fix():
    #with myfix() as f:
        #yield f


#@pytest.mark.parametrize('name', ('a', 'b', 'c'))
#def test_trade_history(mod_fix, name):
    #assert mod_fix.out(name)
def test_trade_history_attach():
    list1 = [{'globalTradeID':0, 'time':1.},
             {'globalTradeID':1, 'time':2.},
             {'globalTradeID':2, 'time':3.}]

    list2 = [{'globalTradeID':1, 'time':2.},
             {'globalTradeID':2, 'time':3.},
             {'globalTradeID':3, 'time':4.}]

    list3 = [{'globalTradeID':2, 'time':3.},
             {'globalTradeID':3, 'time':4.},
             {'globalTradeID':4, 'time':5.}]

    list4 = [{'globalTradeID':5, 'time':6.},
             {'globalTradeID':6, 'time':7.},
             {'globalTradeID':7, 'time':8.}]

    h = trader.TradeHistory('BTC_XMR')
    h._attach_data(list2)
    assert(h.count() == 3)
    h._attach_data(list3)
    assert(h.count() == 4)
    h._attach_data(list1)
    assert(h.count() == 5)

    with pytest.raises(ValueError):
        h._attach_data(list4)

    pprint(h.data())


@pytest.mark.skip()
def test_trade_history():
    h = trader.TradeHistory('BTC_XMR', step_size_sec=60)
    for i in range(2):
        h.fetch_next()
        print(time.time() - h.last_time())

        print(h)
        time.sleep(20)

if __name__ == '__main__':
    pytest.main()
