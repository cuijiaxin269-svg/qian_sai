from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app.constants import DEFAULT_DATA_SAVE_DIR
from models.measurement import MeasurementRecord, format_capacitance
from services.scan_service import ScanConfig, ScanService
from storage.csv_store import save_records
from ui.widgets import CurvePlot, group


class ScanTab(QWidget):
    def __init__(self, scan: ScanService, notify) -> None:
        super().__init__()
        self._scan = scan
        self._notify = notify
        self._records: list[MeasurementRecord] = []
        self._curves: dict[str, list[MeasurementRecord]] = {"Ciss": [], "Coss": [], "Crss": []}
        self._build_ui()
        self._scan.point_received.connect(self._on_point)
        self._scan.progress_changed.connect(self._on_progress)
        self._scan.finished.connect(self._on_finished)
        self._scan.failed.connect(self._on_failed)
        self._scan.running_changed.connect(self._on_running_changed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        title = QLabel("C-V 曲线扫描")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        config_box, config_layout = group("扫描参数")
        form = QFormLayout()
        self.curve_selection = QComboBox()
        self.curve_selection.addItem("Ciss", ("Ciss",))
        self.curve_selection.addItem("Crss", ("Crss",))
        self.curve_selection.addItem("Coss", ("Coss",))
        self.curve_selection.addItem("三个曲线同时扫描", ("Ciss", "Coss", "Crss"))
        self.start_v = QLabel("0.1 V（固定）")
        self.stop_v = QDoubleSpinBox()
        self.stop_v.setRange(0.2, 99.2)
        self.stop_v.setValue(99.2)
        self.stop_v.setDecimals(2)
        self.stop_v.setSingleStep(0.5)
        self.stop_v.setSuffix(" V")
        form.addRow("扫描曲线：", self.curve_selection)
        form.addRow("起始电压：", self.start_v)
        form.addRow("终止偏压：", self.stop_v)
        config_layout.addLayout(form)
        path_line = QHBoxLayout()
        self.save_dir = QLineEdit(DEFAULT_DATA_SAVE_DIR)
        browse = QPushButton("选择保存位置")
        browse.clicked.connect(self._browse)
        path_line.addWidget(self.save_dir)
        path_line.addWidget(browse)
        config_layout.addLayout(path_line)
        actions = QHBoxLayout()
        self.start_button = QPushButton("开始扫描")
        self.start_button.setObjectName("primaryAction")
        self.start_button.clicked.connect(self._start)
        self.stop_button = QPushButton("停止扫描")
        self.stop_button.setObjectName("dangerAction")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._scan.stop)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        config_layout.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        config_layout.addWidget(self.progress)
        self.status = QLabel("状态：等待开始扫描")
        self.status.setObjectName("statusText")
        config_layout.addWidget(self.status)
        layout.addWidget(config_box)

        chart_box, chart_layout = group("C-V 曲线")
        chart_actions = QHBoxLayout()
        chart_actions.addWidget(QLabel("可同时叠加显示 Ciss、Coss、Crss 三条曲线"))
        chart_actions.addStretch()
        clear_curves = QPushButton("清空全部曲线")
        clear_curves.setObjectName("clearAction")
        clear_curves.clicked.connect(self._clear_curves)
        chart_actions.addWidget(clear_curves)
        chart_layout.addLayout(chart_actions)
        self.chart = CurvePlot()
        chart_layout.addWidget(self.chart)
        layout.addWidget(chart_box, 1)

        table_box, table_layout = group("扫描数据")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["序号", "类型", "实际偏压", "电容", "质量"])
        self.table.horizontalHeader().setStretchLastSection(True)
        table_layout.addWidget(self.table)
        layout.addWidget(table_box, 1)
        self._apply_style()

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择 C-V 数据保存位置", self.save_dir.text())
        if directory:
            self.save_dir.setText(directory)

    def _start(self) -> None:
        try:
            self._records = []
            cap_types = self.curve_selection.currentData()
            is_triple = len(cap_types) == 3
            if is_triple:
                self._curves = {"Ciss": [], "Coss": [], "Crss": []}
                self.chart.clear()
                self._last_scan_name = "Ciss_Coss_Crss"
            else:
                cap_type = cap_types[0]
                self._curves[cap_type] = []
                self.chart.clear_curve(cap_type)
                self._last_scan_name = cap_type
            self.table.setRowCount(0)
            self.progress.setValue(0)
            self._scan.start(ScanConfig(cap_types, self.stop_v.value()))
        except Exception as exc:
            self.status.setText(f"状态：无法开始扫描：{exc}")

    def _on_point(self, record: MeasurementRecord) -> None:
        self._records.append(record)
        if record.valid and record.bias_actual_v is not None:
            self._curves[record.cap_type].append(record)
            self.chart.set_curve_points(
                record.cap_type,
                [(item.bias_actual_v, item.capacitance_pf) for item in self._curves[record.cap_type]],
            )
        row = self.table.rowCount()
        self.table.insertRow(row)
        quality = "有效" if record.valid else "无效"
        bias_text = "--" if record.bias_actual_v is None else f"{record.bias_actual_v:.2f} V"
        for column, text in enumerate([str(row + 1), record.cap_type, bias_text, format_capacitance(record.capacitance_f), quality]):
            self.table.setItem(row, column, QTableWidgetItem(text))

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status.setText(f"状态：{message}")

    def _on_running_changed(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _on_failed(self, message: str) -> None:
        self.status.setText(f"状态：{message}")
        self._notify(message)

    def _on_finished(self, records: list[MeasurementRecord]) -> None:
        self.progress.setValue(100 if records else 0)
        self.status.setText(f"状态：扫描结束，已采集 {len(records)} 个点")
        if records:
            try:
                path = save_records(records, self.save_dir.text(), f"CV_{getattr(self, '_last_scan_name', 'scan')}")
                self._notify(f"C-V 数据已保存：{path}")
            except OSError as exc:
                self._notify(f"C-V 数据保存失败：{exc}")

    def _clear_curves(self) -> None:
        if self._scan.is_running:
            self.status.setText("状态：扫描进行中，不能清空曲线")
            return
        self._curves = {"Ciss": [], "Coss": [], "Crss": []}
        self.chart.clear()
        self.table.setRowCount(0)
        self.status.setText("状态：三条曲线已清空")

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget { background: #f4f7fb; color: #162033; font-size: 14px; }
            QLabel#pageTitle { font-size: 28px; font-weight: 700; color: #12213d; }
            QGroupBox { background: white; border: 1px solid #dfe7f2; border-radius: 12px; margin-top: 12px; padding: 14px; font-weight: 700; color: #1e3a5f; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
            QLabel#statusText { color: #60708b; font-weight: 500; }
            QPushButton { border-radius: 7px; padding: 9px 16px; font-weight: 600; background: white; border: 1px solid #bdcadb; }
            QPushButton#primaryAction { background: #1677d2; border-color: #1677d2; color: white; }
            QPushButton#dangerAction { background: #fff5f5; border-color: #f1b5b5; color: #b42318; }
            QPushButton#clearAction { background: #f8fafc; color: #475569; border-color: #cbd5e1; }
            QComboBox, QDoubleSpinBox, QLineEdit { background: white; border: 1px solid #bdcadb; border-radius: 6px; padding: 7px; }
            QProgressBar { border: 1px solid #d9e2ef; border-radius: 6px; text-align: center; height: 16px; } QProgressBar::chunk { background: #1677d2; border-radius: 5px; }
            QTableWidget { border: 1px solid #e2e8f0; gridline-color: #e9eef5; }
        """)
