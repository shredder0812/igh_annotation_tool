import numpy as np
from sortedcontainers import SortedDict, SortedSet
from PyQt5.QtCore import QPoint, Qt, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QLabel


class _BasePredictionBar(QLabel):
    clicked = pyqtSignal(QPoint)
    dragged = pyqtSignal(QPoint)
    lengthChanged = pyqtSignal(int)
    predictionsChanged = pyqtSignal()
    predictionsAdded = pyqtSignal(object)
    annotationsAdded = pyqtSignal(object)
    annotationsChanged = pyqtSignal()
    predictionsRemoved = pyqtSignal(object)
    annotationsRemoved = pyqtSignal(object)
    idsChanged = pyqtSignal(object)
    thresholdChanged = pyqtSignal(float)

    cmap = {
        None: [180, 180, 180],
        0: [180, 180, 180],
        1: [200, 200, 0],
        2: [0, 255, 0],
        3: [255, 0, 0],
        4: [200, 0, 200],
    }

    presence_highlight = [0, 0, 255]

    def __init__(self, parent=None):
        QLabel.__init__(self, parent)
        self.threshold = 0
        self.setMouseTracking(True)
        self.setMinimumSize(1, 1)
        self.length = 1
        self.annotations = SortedDict()
        self.predictions = SortedDict()
        self.pixels = {0: SortedSet(), 1: SortedSet(), 2: SortedSet()}
        self.cvImage = np.zeros((1, 1, 3), dtype=np.uint8)
        self.ids = SortedSet()
        self.filtered_ids = SortedSet()
        self.idsChanged.connect(self.filterIds)
        self.thresholdChanged.connect(self.filterIds)
        self.lengthChanged.connect(self.resetIds)
        self.annotationsAdded.connect(self.addIdsFromDict)
        self.predictionsAdded.connect(self.addIdsFromDict)
        self.predictionsAdded.connect(self.predictionsChanged)
        self.predictionsRemoved.connect(self.predictionsChanged)
        self.annotationsAdded.connect(self.annotationsChanged)
        self.annotationsRemoved.connect(self.annotationsChanged)
        self.show()

    def filterIds(self):
        self.filtered_ids = SortedSet(
            filter(
                lambda id: id == 0
                or id == self.length - 1
                or (id in self.predictions and self.predictions[id][0][-1] >= self.threshold)
                or (id in self.annotations),
                self.ids,
            )
        )

    def setThreshold(self, threshold):
        self.threshold = threshold
        self.thresholdChanged.emit(self.threshold)

    def resetIds(self):
        self.ids.clear()
        self.ids.add(0)
        if self.length > 0:
            self.ids.add(self.length - 1)
        self.idsChanged.emit(self.ids)

    def addIdsFromDict(self, additions=None):
        if additions is not None:
            for _ in additions.keys():
                self.ids.add(_)
        self.idsChanged.emit(self.ids)

    def addId(self, id):
        if id not in self.ids:
            self.ids.add(id)
            self.idsChanged.emit(self.ids)

    def removeId(self, id):
        if id not in set(self.annotations.keys()).union(self.predictions.keys()):
            self.ids.remove(id)
            self.idsChanged.emit(self.ids)

    def setLength(self, length):
        self.length = length
        self.clear()
        self.lengthChanged.emit(self.length)

    def setPredictions(self, predictions):
        self.clearPredictions(False)
        self.predictions.update(predictions)
        self.predictionsAdded.emit(predictions)
        self.redraw()

    def addPredictions(self, predictions):
        self.predictions.update(predictions)
        self.predictionsAdded.emit(predictions)
        self.redraw()

    def removePrediction(self, id):
        if id in self.predictions:
            for _ in [2]:
                self.pixels[_].pop(id)
            self.predictionsRemoved.emit({id: self.predictions.pop(id)})
            self.redraw()

    def setAnnotations(self, annotations):
        self.clearAnnotations(False)
        self.annotations.update(annotations)
        self.annotationsAdded.emit(annotations)
        self.redraw()

    def addAnnotations(self, annotations):
        self.annotations.update(annotations)
        self.annotationsAdded.emit(annotations)
        self.redraw()

    def removeAnnotation(self, id):
        if id in self.annotations:
            for _ in [0, 1]:
                self.pixels[_].clear()
            self.annotationsRemoved.emit({id: self.annotations.pop(id)})
            self.redraw()

    def redraw(self):
        scale = (self.width() - 1) / (self.length - 1) if self.length > 1 else 0
        for _ in self.pixels.keys():
            self.pixels[_].clear()
        self.pixels[0].update(
            map(lambda ann: round(ann[0] * scale), filter(lambda ann: len(ann[1]) == 0, self.annotations.items()))
        )
        self.pixels[1].update(
            map(lambda ann: round(ann[0] * scale), filter(lambda ann: len(ann[1]) > 0, self.annotations.items()))
        )
        self.pixels[2].update(
            map(
                lambda pred: round(pred[0] * scale),
                filter(lambda pred: any(obj[-1] >= self.threshold for obj in pred[1]), self.predictions.items()),
            )
        )
        self.show()

    def show(self):
        if self.cvImage.shape[1] != self.width():
            self.cvImage = np.zeros((1, self.width(), 3), dtype=np.uint8)
        self.cvImage[:, :] = self.cmap[None]
        for _ in [0, 1]:
            if len(self.pixels[_]) > 0:
                self.cvImage[:, list(self.pixels[_])] = self.cmap[_]
        if len(self.pixels[2]) > 0:
            pred = set(self.pixels[2])
            fn = tuple(pred.difference(list(self.pixels[0]) + list(self.pixels[1])))
            fp = tuple(pred.intersection(self.pixels[0]))
            tp = tuple(pred.intersection(self.pixels[1]))
            self.cvImage[:, fn] = self.cmap[2]
            self.cvImage[:, tp] = self.cmap[3]
            self.cvImage[:, fp] = self.cmap[4]

        for pixel in self.pixels[1]:
            self.cvImage[:, pixel - 1 : pixel + 2] = self.presence_highlight

        pixmap = QPixmap.fromImage(
            QImage(self.cvImage.data, self.cvImage.shape[1], self.cvImage.shape[0], QImage.Format_RGB888)
        )
        self.setPixmap(pixmap.scaled(self.size()))

    def clearPredictions(self, redraw=True):
        self.predictions.clear()
        for _ in [0, 1]:
            self.pixels[_].clear()
        if redraw:
            self.redraw()

    def clearAnnotations(self, redraw=True):
        self.annotations.clear()
        for _ in [2]:
            self.pixels[_].clear()
        if redraw:
            self.redraw()

    def clear(self, redraw=True):
        self.clearPredictions(False)
        self.clearAnnotations(False)
        self.resetIds()
        if redraw:
            self.redraw()

    def resizeEvent(self, ev):
        self.cvImage = np.zeros((1, self.width(), 3), dtype=np.uint8)
        for _ in self.pixels.keys():
            self.pixels[_].clear()
        self.redraw()

    def mousePressevent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(ev.pos())

    def _pixelPosToFrame(self, pos):
        if self.length <= 1:
            return 0
        scale = (self.length - 1) / (self.width() - 1)
        return round(pos * scale)

    def mouseMoveEvent(self, ev):
        if ev.buttons() == Qt.LeftButton:
            self.dragged.emit(ev.pos())

    def setRange(self, start, end):
        if start >= 0 and end >= start:
            self.length = end - start + 1
            self.lengthChanged.emit(self.length)
            self.resetIds()
            self.redraw()


class QPredictionBar(_BasePredictionBar):
    presence_highlight = [0, 0, 255]


class QPredictionBar_MOT(_BasePredictionBar):
    presence_highlight = [255, 208, 23]


class QBar_PointerObject(_BasePredictionBar):
    cmap = {
        None: [240, 240, 240],
        0: [180, 180, 180],
        1: [200, 200, 0],
        2: [0, 255, 0],
        3: [255, 0, 0],
        4: [200, 0, 200],
    }
    presence_highlight = [255, 0, 0]
