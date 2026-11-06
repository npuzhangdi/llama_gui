# -*- coding: utf-8 -*-
"""轻量线性图标：全部用 QPainter 绘制，不依赖图片资源或图标字体。"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen

_D = 24.0


def draw_icon(painter: QPainter, rect: QRectF, kind: str, color: str | QColor, weight: float = 1.8) -> None:
    """在 rect 内绘制 24x24 设计坐标系下的线性图标。"""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color))
    pen.setWidthF(weight)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    u = min(rect.width(), rect.height()) / _D
    ox, oy = rect.left(), rect.top()

    def p(x, y):
        return QPointF(ox + x * u, oy + y * u)

    def line(x1, y1, x2, y2):
        painter.drawLine(p(x1, y1), p(x2, y2))

    def poly(points, closed=False):
        from PySide6.QtGui import QPainterPath
        path = QPainterPath()
        path.moveTo(p(*points[0]))
        for xy in points[1:]:
            path.lineTo(p(*xy))
        if closed:
            path.closeSubpath()
        painter.drawPath(path)

    def rrect(x, y, w, h, r=3):
        painter.drawRoundedRect(QRectF(p(x, y), p(x + w, y + h)), r * u, r * u)

    def circle(x, y, r):
        painter.drawEllipse(p(x, y), r * u, r * u)

    if kind == "chat":
        poly([(4, 5), (20, 5), (20, 16), (10, 16), (6, 20), (6, 16), (4, 16)], closed=True)
        line(8, 10, 16, 10)
        line(8, 13, 13, 13)
    elif kind == "server":
        rrect(3, 4, 18, 7, 2.5)
        rrect(3, 13, 18, 7, 2.5)
        circle(7, 7.5, 0.9)
        circle(7, 16.5, 0.9)
        line(11, 7.5, 18, 7.5)
        line(11, 16.5, 18, 16.5)
    elif kind == "cube":
        poly([(12, 3), (20, 7.5), (20, 16.5), (12, 21), (4, 16.5), (4, 7.5)], closed=True)
        poly([(4, 7.5), (12, 12), (20, 7.5)])
        line(12, 12, 12, 21)
    elif kind == "terminal":
        rrect(3, 4, 18, 16, 3)
        line(6.5, 9, 9.5, 11.5)
        line(6.5, 11.5, 9.5, 9)
        line(12, 11.5, 17, 11.5)
        line(6.5, 15.5, 15, 15.5)
    elif kind == "sun":
        circle(12, 12, 4)
        for dx, dy in ((0, -7.5), (0, 7.5), (-7.5, 0), (7.5, 0), (-5.3, -5.3), (5.3, -5.3), (-5.3, 5.3), (5.3, 5.3)):
            x, y = 12 + dx, 12 + dy
            line(x - dx * 0.18, y - dy * 0.18, x + dx * 0.18, y + dy * 0.18)
    elif kind == "moon":
        poly([(15.5, 3.5), (9.5, 5.5), (7, 11), (9, 17), (14.5, 20.5), (18, 19), (13.5, 15), (12, 9)], closed=True)
    elif kind == "sparkle":
        poly([(12, 2.5), (14.2, 9.8), (21.5, 12), (14.2, 14.2), (12, 21.5),
              (9.8, 14.2), (2.5, 12), (9.8, 9.8)], closed=True)
    elif kind == "copy":
        rrect(8, 8, 12, 12, 2.5)
        poly([(16, 8), (16, 5), (5, 5), (5, 16), (8, 16)])
    elif kind == "stop":
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(p(7, 7), p(17, 17)), 2 * u, 2 * u)
    elif kind == "send":
        poly([(4, 12), (20, 4), (14, 20), (11.5, 13.5)])
        line(11.5, 13.5, 20, 4)
    elif kind == "refresh":
        poly([(19, 10), (19, 5), (14, 5)])
        painter.drawArc(QRectF(p(4, 4), p(20, 20)), 60 * 16, 250 * 16)
        poly([(5, 14), (5, 19), (10, 19)])
    elif kind == "folder":
        poly([(3, 7), (9, 7), (11, 9), (21, 9), (21, 19), (3, 19)], closed=True)
    elif kind == "plus":
        line(12, 5, 12, 19)
        line(5, 12, 19, 12)
    elif kind == "trash":
        poly([(4, 7), (20, 7)])
        poly([(9, 7), (9, 4), (15, 4), (15, 7)])
        poly([(6, 7), (7, 20), (17, 20), (18, 7)], closed=True)
        line(10, 11, 10, 17)
        line(14, 11, 14, 17)
    elif kind == "power":
        painter.drawArc(QRectF(p(5, 5), p(19, 19)), 130 * 16, 280 * 16)
        line(12, 3, 12, 11)
    elif kind == "chevron_down":
        poly([(7, 10), (12, 15), (17, 10)])
    elif kind == "chevron_right":
        poly([(10, 7), (15, 12), (10, 17)])
    elif kind == "close":
        line(6, 6, 18, 18)
        line(18, 6, 6, 18)
    elif kind == "minimize":
        line(5, 12, 19, 12)
    elif kind == "maximize":
        rrect(5.5, 5.5, 13, 13, 2)
    elif kind == "check":
        poly([(5, 12.5), (10, 17), (19, 7)])
    elif kind == "info":
        circle(12, 12, 9)
        line(12, 11, 12, 16)
        circle(12, 7.5, 0.6)
    elif kind == "sliders":
        line(4, 7, 20, 7)
        line(4, 12, 20, 12)
        line(4, 17, 20, 17)
        circle(9, 7, 1.8)
        circle(15, 12, 1.8)
        circle(8, 17, 1.8)
    elif kind == "bolt":
        poly([(13, 3), (6, 13), (11, 13), (10, 21), (18, 10), (13, 10)], closed=True)
    elif kind == "settings":
        # 齿轮：双同心圆 + 八条齿，线性风格与其余图标一致
        circle(12, 12, 3.1)
        circle(12, 12, 7.2)
        for k in range(8):
            a = math.radians(k * 45)
            dx, dy = math.cos(a), math.sin(a)
            line(12 + 7.2 * dx, 12 + 7.2 * dy, 12 + 10 * dx, 12 + 10 * dy)
    elif kind == "archive":
        rrect(3, 4, 18, 4, 1.5)
        poly([(5, 8), (5, 20), (19, 20), (19, 8)])
        line(10, 12, 14, 12)

    painter.restore()
