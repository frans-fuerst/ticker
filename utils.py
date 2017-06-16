#!/usr/bin/env python3

import sys
import signal
import logging as log
from PyQt4 import QtGui, QtCore, Qt
import qwt


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

        self.plot = DataPlot()
        self.layout().addWidget(self.plot)
        self.setGeometry(200, 200, 1100, 650)

        self.plot.redraw()

    def set_data(self, xdata, ydata, pen=None):
        used_pen = {
            'fat_blue': Qt.QPen(Qt.Qt.blue, 2, Qt.Qt.SolidLine),
            'fat_red': Qt.QPen(Qt.Qt.red, 2, Qt.Qt.SolidLine),
            'fat_green': Qt.QPen(Qt.Qt.green, 2, Qt.Qt.SolidLine),
            None: Qt.QPen(Qt.Qt.black, 1, Qt.Qt.SolidLine),
            }[pen]
        self.plot.set_data(xdata, ydata, used_pen)
        self.plot.redraw()

class qtapp:
    def __enter__(self, *args):
        self.app = QtGui.QApplication(sys.argv)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        return self

    def __exit__(self, *args):
        pass

    def run(self):
        return self.app.exec_()



def main():
    log.basicConfig(level=log.INFO)
    with qtapp() as app:
        w = GraphUI()
        w.show()
        app.run()

if __name__ == '__main__':
    main()

