import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGroupBox, QLabel, QPushButton, QVBoxLayout, QWidget


def group(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    return box, layout


def placeholder(title: str, message: str) -> QGroupBox:
    box, layout = group(title)
    layout.addWidget(QLabel(message))
    button = QPushButton("暂不可用")
    button.setEnabled(False)
    layout.addWidget(button)
    return box


class CurvePlot(QWidget):
    """无需额外依赖的简易 C-V 曲线显示组件。

    真实采样点始终以圆点显示；当点数不少于 3 时，使用单调三次插值
    绘制平滑线，避免普通高阶拟合在电容曲线上出现不合理的过冲。
    """

    def __init__(self) -> None:
        super().__init__()
        self._curves: dict[str, list[tuple[float, float]]] = {}
        self._colors = {
            "Ciss": QColor("#1677d2"),
            "Coss": QColor("#d97706"),
            "Crss": QColor("#7c3aed"),
        }
        self.setMinimumHeight(460)

    def clear(self) -> None:
        self._curves.clear()
        self.update()

    def clear_curve(self, curve_name: str) -> None:
        self._curves.pop(curve_name, None)
        self.update()

    def set_curve_points(self, curve_name: str, points: list[tuple[float, float]]) -> None:
        self._curves[curve_name] = sorted(points, key=lambda point: point[0])
        self.update()

    def add_point(self, voltage_v: float, capacitance_pf: float, curve_name: str = "当前扫描") -> None:
        self._curves.setdefault(curve_name, []).append((voltage_v, capacitance_pf))
        self._curves[curve_name].sort(key=lambda point: point[0])
        self.update()

    @staticmethod
    def _smooth_points(points: list[tuple[float, float]], samples_per_segment: int = 28) -> list[tuple[float, float]]:
        """Fritsch-Carlson 单调三次 Hermite 插值，适合稀疏且单调的 C-V 数据。"""
        if len(points) < 3:
            return points
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        h = [xs[index + 1] - xs[index] for index in range(len(xs) - 1)]
        slopes = [(ys[index + 1] - ys[index]) / h[index] for index in range(len(h))]
        tangents = [slopes[0]]
        for index in range(1, len(xs) - 1):
            if slopes[index - 1] * slopes[index] <= 0:
                tangents.append(0.0)
            else:
                # PCHIP 加权调和平均：曲线更圆润，且不会跨越相邻真实点。
                previous_h, next_h = h[index - 1], h[index]
                left_weight = 2 * next_h + previous_h
                right_weight = next_h + 2 * previous_h
                tangents.append((left_weight + right_weight) / (
                    left_weight / slopes[index - 1] + right_weight / slopes[index]
                ))
        tangents.append(slopes[-1])
        # 限制每段两端切线，确保插值不超出相邻采样值范围。
        for index, slope in enumerate(slopes):
            if slope == 0:
                tangents[index] = tangents[index + 1] = 0.0
                continue
            alpha, beta = tangents[index] / slope, tangents[index + 1] / slope
            radius = alpha * alpha + beta * beta
            if radius > 9:
                scale = 3 / radius ** 0.5
                tangents[index] = scale * alpha * slope
                tangents[index + 1] = scale * beta * slope
        result: list[tuple[float, float]] = []
        for index in range(len(h)):
            for sample in range(samples_per_segment):
                t = sample / samples_per_segment
                t2, t3 = t * t, t * t * t
                h00, h10 = 2 * t3 - 3 * t2 + 1, t3 - 2 * t2 + t
                h01, h11 = -2 * t3 + 3 * t2, t3 - t2
                result.append((
                    xs[index] + t * h[index],
                    h00 * ys[index] + h10 * h[index] * tangents[index]
                    + h01 * ys[index + 1] + h11 * h[index] * tangents[index + 1],
                ))
        result.append(points[-1])
        return result

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        rect = self.rect().adjusted(88, 24, -26, -68)
        non_empty_curves = {name: points for name, points in self._curves.items() if points}
        if not non_empty_curves:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(rect, Qt.AlignCenter, "完成 Ciss、Coss、Crss 扫描后可叠加显示曲线")
            return
        all_points = [point for points in non_empty_curves.values() for point in points if point[0] > 0 and point[1] > 0]
        if not all_points:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(rect, Qt.AlignCenter, "对数坐标仅显示偏压和电容均大于 0 的有效数据")
            return
        xs, ys = zip(*all_points)
        min_x, max_x = self._log_bounds(min(xs), max(xs))
        min_y, max_y = self._log_bounds(min(ys), max(ys))
        x_ticks = self._log_ticks(min_x, max_x)
        y_ticks = self._log_ticks(min_y, max_y)

        painter.setPen(QPen(QColor("#dce5f0"), 1))
        for value in x_ticks:
            px = self._map_log(value, min_x, max_x, rect.left(), rect.right())
            painter.drawLine(int(px), rect.top(), int(px), rect.bottom())
        for value in y_ticks:
            py = self._map_log(value, min_y, max_y, rect.bottom(), rect.top())
            painter.drawLine(rect.left(), int(py), rect.right(), int(py))

        axis_pen = QPen(QColor("#64748b"), 1.2)
        painter.setPen(axis_pen)
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        painter.drawLine(rect.left(), rect.top(), rect.left(), rect.bottom())
        painter.setPen(QColor("#475569"))
        for value in x_ticks:
            px = self._map_log(value, min_x, max_x, rect.left(), rect.right())
            painter.drawLine(int(px), rect.bottom(), int(px), rect.bottom() + 5)
            painter.drawText(int(px) - 24, rect.bottom() + 22, 48, 16, Qt.AlignHCenter, self._tick_label(value))
        for value in y_ticks:
            py = self._map_log(value, min_y, max_y, rect.bottom(), rect.top())
            painter.drawLine(rect.left() - 5, int(py), rect.left(), int(py))
            painter.drawText(4, int(py) - 8, rect.left() - 12, 16, Qt.AlignRight | Qt.AlignVCenter, self._tick_label(value))
        painter.drawText(rect.center().x() - 105, self.height() - 16, "偏压 VBIAS (V，对数坐标)")
        painter.save()
        painter.translate(19, rect.center().y() + 65)
        painter.rotate(-90)
        painter.drawText(0, 0, "电容 (pF，对数坐标)")
        painter.restore()
        for curve_name, points in non_empty_curves.items():
            color = self._colors.get(curve_name, QColor("#475569"))
            path = QPainterPath()
            for index, (x, y) in enumerate(self._smooth_points(points)):
                if x <= 0 or y <= 0:
                    continue
                px = self._map_log(x, min_x, max_x, rect.left(), rect.right())
                py = self._map_log(y, min_y, max_y, rect.bottom(), rect.top())
                if index == 0:
                    path.moveTo(QPointF(px, py))
                else:
                    path.lineTo(QPointF(px, py))
            curve_pen = QPen(color, 3.2)
            curve_pen.setCapStyle(Qt.RoundCap)
            curve_pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(curve_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
            painter.setPen(QPen(QColor("#ffffff"), 1))
            painter.setBrush(color)
            for x, y in points:
                if x <= 0 or y <= 0:
                    continue
                px = self._map_log(x, min_x, max_x, rect.left(), rect.right())
                py = self._map_log(y, min_y, max_y, rect.bottom(), rect.top())
                painter.drawEllipse(QPointF(px, py), 3, 3)
        legend_x, legend_y = rect.right() - 105, rect.top() + 8
        for index, curve_name in enumerate(non_empty_curves):
            color = self._colors.get(curve_name, QColor("#475569"))
            y = legend_y + index * 20
            painter.setPen(QPen(color, 3))
            painter.drawLine(legend_x, y, legend_x + 20, y)
            painter.setPen(QColor("#334155"))
            painter.drawText(legend_x + 28, y + 5, curve_name)

    @staticmethod
    def _log_bounds(minimum: float, maximum: float) -> tuple[float, float]:
        low = math.log10(minimum)
        high = math.log10(maximum)
        if math.isclose(low, high):
            low -= 0.5
            high += 0.5
        else:
            padding = (high - low) * 0.06
            low -= padding
            high += padding
        return low, high

    @staticmethod
    def _map_log(value: float, minimum: float, maximum: float, start: float, end: float) -> float:
        return start + (math.log10(value) - minimum) / (maximum - minimum) * (end - start)

    @staticmethod
    def _log_ticks(minimum: float, maximum: float) -> list[float]:
        ticks: list[float] = []
        for exponent in range(math.floor(minimum), math.ceil(maximum) + 1):
            for multiplier in (1, 2, 5):
                value = multiplier * (10 ** exponent)
                logarithm = math.log10(value)
                if minimum <= logarithm <= maximum:
                    ticks.append(value)
        return ticks

    @staticmethod
    def _tick_label(value: float) -> str:
        if value >= 1000 or value < 0.01:
            return f"{value:.0e}"
        if value >= 10:
            return f"{value:.0f}"
        if value >= 1:
            return f"{value:.1f}".rstrip("0").rstrip(".")
        return f"{value:.2f}".rstrip("0").rstrip(".")
