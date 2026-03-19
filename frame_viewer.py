import logging

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QCursor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QLabel


class VideoFrameViewer(QLabel):
    _PEN_STYLE_MAP = {
        "Qt.NoPen": Qt.NoPen,
        "Qt.SolidLine": Qt.SolidLine,
        "Qt.DashLine": Qt.DashLine,
        "Qt.DotLine": Qt.DotLine,
        "Qt.DashDotLine": Qt.DashDotLine,
        "Qt.DashDotDotLine": Qt.DashDotDotLine,
    }

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.logger = logging.getLogger(__name__)
        self.is_drawing = False
        self.is_selecting = False
        self.pt1 = self.pt2 = None
        self.select_pt1 = self.select_pt2 = None

        self.scale_factor = 1

        self.draw_color = QColor(0, 0, 0)
        self.draw_thickness = 1
        self.draw_style = Qt.SolidLine

        self.select_color = QColor(0, 0, 0)
        self.select_thickness = 2
        self.select_style = Qt.SolidLine

        cursor_image = QPixmap(3000, 3000)
        cursor_image.fill(Qt.transparent)
        painter = QPainter(cursor_image)
        painter.setPen(Qt.red)
        painter.drawLine(1500, 0, 1500, 3000)
        painter.drawLine(0, 1500, 3000, 1500)
        painter.end()
        cursor = QCursor(cursor_image, 1500, 1500)
        self.setCursor(cursor)

    @classmethod
    def _normalize_pen_color(cls, value, fallback=QColor(0, 0, 0)):
        if isinstance(value, QColor):
            return value

        if isinstance(value, (tuple, list)) and len(value) in (3, 4):
            try:
                channels = [int(v) for v in value]
                return QColor(*channels)
            except (TypeError, ValueError):
                return fallback

        if isinstance(value, str):
            color = QColor(value)
            if color.isValid():
                return color

        return fallback

    @classmethod
    def _normalize_pen_style(cls, value, fallback=Qt.SolidLine):
        if isinstance(value, Qt.PenStyle):
            return value

        if isinstance(value, int):
            try:
                return Qt.PenStyle(value)
            except ValueError:
                return fallback

        if isinstance(value, str):
            return cls._PEN_STYLE_MAP.get(value, fallback)

        return fallback

    def apply_draw_config(self, color=None, thickness=None, style=None):
        self.draw_color = self._normalize_pen_color(color, fallback=self.draw_color)
        if thickness is not None:
            self.draw_thickness = max(1, int(thickness))
        self.draw_style = self._normalize_pen_style(style, fallback=self.draw_style)

    def apply_select_config(self, color=None, thickness=None, style=None):
        self.select_color = self._normalize_pen_color(color, fallback=self.select_color)
        if thickness is not None:
            self.select_thickness = max(1, int(thickness))
        self.select_style = self._normalize_pen_style(style, fallback=self.select_style)

    def revise_coor(self, pt1: tuple, pt2: tuple):
        revise_pt1 = (min(pt1[0], pt2[0]), min(pt1[1], pt2[1]))
        revise_pt2 = (max(pt1[0], pt2[0]), max(pt1[1], pt2[1]))
        return (revise_pt1, revise_pt2)

    def _draw_rect(self, pt1: tuple, pt2: tuple, pen: QPen):
        painter = QPainter()
        painter.begin(self)
        painter.setPen(pen)
        pt1_x, pt1_y, pt2_x, pt2_y = pt1[0], pt1[1], pt2[0], pt2[1]
        width, height = (pt2_x - pt1_x), (pt2_y - pt1_y)
        painter.drawRect(pt1_x, pt1_y, width, height)
        painter.end()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.is_drawing and self.pt1 and self.pt2:
            pen = QPen(
                self._normalize_pen_color(self.draw_color),
                int(max(1, self.draw_thickness)),
                self._normalize_pen_style(self.draw_style),
            )
            pt1, pt2 = self.revise_coor(self.pt1, self.pt2)
            self._draw_rect(pt1, pt2, pen)
        elif not self.is_drawing and self.select_pt1 and self.select_pt2:
            pen = QPen(
                self._normalize_pen_color(self.select_color),
                int(max(1, self.select_thickness)),
                self._normalize_pen_style(self.select_style),
            )
            pt1, pt2 = self.revise_coor(self.select_pt1, self.select_pt2)
            self._draw_rect(pt1, pt2, pen)
