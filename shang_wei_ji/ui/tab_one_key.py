from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from app.constants import DEFAULT_DATA_SAVE_DIR
from models.measurement import MeasurementRecord, format_capacitance
from services.one_key_service import OneKeyService
from storage.csv_store import save_records
from ui.widgets import group


class OneKeyTab(QWidget):
    def __init__(self, one_key: OneKeyService, notify) -> None:
        super().__init__()
        self._one_key = one_key
        self._notify = notify
        self._records: list[MeasurementRecord] = []
        self._result_labels: dict[str, QLabel] = {}
        self._build_ui()
        self._one_key.result_received.connect(self._on_result)
        self._one_key.progress_changed.connect(self._on_progress)
        self._one_key.finished.connect(self._on_finished)
        self._one_key.running_changed.connect(self._on_running_changed)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        title = QLabel("Ciss、Coss、Crss 一键测量")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        control_box, control_layout = group("测量设置")
        form = QFormLayout()
        self.bias_v = QDoubleSpinBox()
        self.bias_v.setRange(0.0, 100.0)
        self.bias_v.setDecimals(2)
        self.bias_v.setSuffix(" V")
        form.addRow("测试偏压：", self.bias_v)
        control_layout.addLayout(form)
        line = QHBoxLayout()
        self.save_dir = QLineEdit(DEFAULT_DATA_SAVE_DIR)
        browse = QPushButton("选择保存位置")
        browse.clicked.connect(self._browse)
        line.addWidget(self.save_dir)
        line.addWidget(browse)
        control_layout.addLayout(line)
        actions = QHBoxLayout()
        self.start_button = QPushButton("开始一键测量")
        self.start_button.setObjectName("primaryAction")
        self.start_button.clicked.connect(self._start)
        self.stop_button = QPushButton("复位中止")
        self.stop_button.setObjectName("dangerAction")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._one_key.stop)
        actions.addWidget(self.start_button)
        actions.addWidget(self.stop_button)
        control_layout.addLayout(actions)
        self.progress = QProgressBar()
        control_layout.addWidget(self.progress)
        self.status = QLabel("状态：等待开始一键测量")
        self.status.setObjectName("statusText")
        control_layout.addWidget(self.status)
        layout.addWidget(control_box)

        results_box, results_layout = group("测量结果")
        cards = QGridLayout()
        for index, cap_type in enumerate(("Ciss", "Coss", "Crss")):
            card = QLabel(f"{cap_type}\n--")
            card.setObjectName("resultCard")
            card.setAlignment(Qt.AlignCenter)
            cards.addWidget(card, 0, index)
            self._result_labels[cap_type] = card
        results_layout.addLayout(cards)
        layout.addWidget(results_box)

        history_box, history_layout = group("本次记录")
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["时间", "类型", "电容", "偏压", "质量"])
        self.table.horizontalHeader().setStretchLastSection(True)
        history_layout.addWidget(self.table)
        layout.addWidget(history_box, 1)
        self._apply_style()

    def _browse(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择一键测量数据保存位置", self.save_dir.text())
        if directory:
            self.save_dir.setText(directory)

    def _start(self) -> None:
        try:
            self._records = []
            self.table.setRowCount(0)
            for cap_type, card in self._result_labels.items():
                card.setText(f"{cap_type}\n--")
            self.progress.setValue(0)
            self._one_key.start(self.bias_v.value())
        except Exception as exc:
            self.status.setText(f"状态：无法开始测量：{exc}")

    def _on_result(self, record: MeasurementRecord) -> None:
        self._records.append(record)
        self._result_labels[record.cap_type].setText(f"{record.cap_type}\n{format_capacitance(record.capacitance_f)}")
        quality = "--" if record.quality is None else f"{record.quality:.3f}"
        row = self.table.rowCount()
        self.table.insertRow(row)
        if record.bias_actual_v is not None:
            bias_text = f"{record.bias_actual_v:.2f} V（实际）"
        elif record.bias_set_v is not None:
            bias_text = f"{record.bias_set_v:.2f} V（已确认设置）"
        else:
            bias_text = "未回传"
        for column, text in enumerate([record.timestamp, record.cap_type, format_capacitance(record.capacitance_f), bias_text, quality]):
            self.table.setItem(row, column, QTableWidgetItem(text))

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.status.setText(f"状态：{message}")

    def _on_running_changed(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _on_finished(self, records: list[MeasurementRecord]) -> None:
        self.progress.setValue(100 if records else 0)
        self.status.setText(f"状态：测量结束，已完成 {len(records)}/3 项")
        if records:
            try:
                path = save_records(records, self.save_dir.text(), "OneKey_Ciss_Coss_Crss")
                self._notify(f"一键测量数据已保存：{path}")
            except OSError as exc:
                self._notify(f"一键测量数据保存失败：{exc}")

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QWidget { background: #f4f7fb; color: #162033; font-size: 14px; }
            QLabel#pageTitle { font-size: 28px; font-weight: 700; color: #12213d; }
            QGroupBox { background: white; border: 1px solid #dfe7f2; border-radius: 12px; margin-top: 12px; padding: 14px; font-weight: 700; color: #1e3a5f; }
            QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
            QLabel#statusText { color: #60708b; font-weight: 500; }
            QLabel#resultCard { background: #eef6ff; border: 1px solid #d5e8ff; border-radius: 10px; color: #1258a7; font-size: 20px; font-weight: 700; padding: 22px; }
            QPushButton { border-radius: 7px; padding: 9px 16px; font-weight: 600; background: white; border: 1px solid #bdcadb; }
            QPushButton#primaryAction { background: #1677d2; border-color: #1677d2; color: white; }
            QPushButton#dangerAction { background: #fff5f5; border-color: #f1b5b5; color: #b42318; }
            QDoubleSpinBox, QLineEdit { background: white; border: 1px solid #bdcadb; border-radius: 6px; padding: 7px; }
            QProgressBar { border: 1px solid #d9e2ef; border-radius: 6px; text-align: center; height: 16px; } QProgressBar::chunk { background: #1677d2; border-radius: 5px; }
            QTableWidget { border: 1px solid #e2e8f0; gridline-color: #e9eef5; }
        """)
