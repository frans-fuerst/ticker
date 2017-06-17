#!/usr/bin/env python3

import sys
import signal
import logging as log
from PyQt4 import QtGui, QtCore, Qt
import qwt

GLOBAL = []

def easypen(pen):
    try:
        return {
            'blue': Qt.QPen(Qt.Qt.blue, 1, Qt.Qt.SolidLine),
            'red': Qt.QPen(Qt.Qt.red, 1, Qt.Qt.SolidLine),
            'green': Qt.QPen(Qt.Qt.green, 1, Qt.Qt.SolidLine),
            'fat_blue': Qt.QPen(Qt.Qt.blue, 2, Qt.Qt.SolidLine),
            'fat_red': Qt.QPen(Qt.Qt.red, 2, Qt.Qt.SolidLine),
            'fat_green': Qt.QPen(Qt.Qt.green, 2, Qt.Qt.SolidLine),
            None: Qt.QPen(Qt.Qt.black, 1, Qt.Qt.SolidLine),
            }[pen]
    except:
        return Qt.QPen(Qt.Qt.black, 1, Qt.Qt.SolidLine)

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

    def add_vmarker(self, pos, pen):
        marker = qwt.QwtPlotMarker()
    #        marker.setLabelAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignTop)
        marker.setLineStyle(qwt.QwtPlotMarker.VLine)
        marker.setLinePen(pen)
        marker.setXValue(pos)
        marker.attach(self)

    def add_hmarker(self, pos, pen):
        marker = qwt.QwtPlotMarker()
    #        marker.setLabelAlignment(Qt.Qt.AlignRight | Qt.Qt.AlignTop)
        marker.setLineStyle(qwt.QwtPlotMarker.HLine)
        marker.setLinePen(pen)
        marker.setYValue(pos)
        marker.attach(self)

    def redraw(self):
        self.replot()


class GraphUI(QtGui.QWidget):

    def __init__(self):
        super().__init__()
        self.setLayout(QtGui.QVBoxLayout())

        self.plot = DataPlot()
        self.layout().addWidget(self.plot)
        self.setGeometry(200, 200, 1100, 650)

        GLOBAL.append(self)
        #self.plot.redraw()
        #self.show()

    def set_data(self, xdata, ydata, pen=None):
        self.plot.set_data(xdata, ydata, easypen(pen))
        self.plot.redraw()

    def add_vmarker(self, pos, pen=None):
        self.plot.add_vmarker(pos, easypen(pen))

    def add_hmarker(self, pos, pen=None):
        self.plot.add_hmarker(pos, easypen(pen))


class qtapp:
    def __init__(self, active=True):
        self._active = active

    def __enter__(self, *args):
        if self._active:
            self.app = QtGui.QApplication(sys.argv)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
        return self

    def __exit__(self, *args):
        pass

    def run(self):
        return self.app.exec_() if GLOBAL else None



def main():
    log.basicConfig(level=log.INFO)
    with qtapp() as app:
        w = GraphUI()
        w.show()
        app.run()

if __name__ == '__main__':
    main()

