from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFormLayout,
    QHBoxLayout,
    QMessageBox,
    QGroupBox,
    QCheckBox,
    QTextEdit,
    QToolTip,
    QGraphicsColorizeEffect,
    QStyle,
    QToolButton,
)
from PySide6.QtCore import Signal, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QGuiApplication, QColor

from backend.command_codec import build_full_payload


class CopyableGroupBox(QGroupBox):
    def __init__(self, title, copy_callback, parent=None):
        super().__init__(title, parent)
        self.copy_button = QToolButton(self)
        self.copy_button.setObjectName("CopyButton")
        self.copy_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.copy_button.setIconSize(QSize(14, 14))
        self.copy_button.setFixedSize(20, 20)
        self.copy_button.setCursor(Qt.PointingHandCursor)
        self.copy_button.setToolTip("Copy command")
        self.copy_button.setStyleSheet("QToolButton { border: none; background: transparent; padding: 0; }")
        self.copy_button.clicked.connect(copy_callback)
        self.copy_button.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_button()

    def _reposition_button(self):
        btn = self.copy_button
        if not btn:
            return
        margin = 16
        title_height = self.fontMetrics().height()
        y_offset = max(0, (title_height - btn.height()) // 2)
        btn.move(max(0, self.width() - btn.width() - margin), y_offset)

    def set_copy_visible(self, visible):
        self.copy_button.setVisible(visible)
        if visible:
            self._reposition_button()

    def set_copy_enabled(self, enabled):
        self.copy_button.setEnabled(enabled)


class PixelDetailPanel(QWidget):
    test_requested = Signal(list)  # command bytes
    confirm_ok_requested = Signal()
    mark_mismatch_requested = Signal()
    reset_status_requested = Signal()
    bit_index_changed = Signal(int)  # new bit index
    pattern_toggle_requested = Signal()

    def __init__(self):
        super().__init__()
        self.current_pixel_data = None
        self.current_alt_command = None
        self.setObjectName("PixelDetailPanel")
        self.init_ui()

    def init_ui(self):
        self.setStyleSheet(
            """
            QWidget#PixelDetailPanel { background-color: #0F172A; border-left: 1px solid #1F2937; }
            QGroupBox { font-weight: 600; border: 1px solid #374151; border-radius: 6px; margin-top: 10px; background-color: #111827; color: #F9FAFB; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #F9FAFB; background-color: transparent; }
            QLabel { color: #F9FAFB; font-size: 13px; }
            QLineEdit { background: #1F2937; color: #F9FAFB; border: 1px solid #475569; border-radius: 4px; padding: 4px; }
            QLineEdit:disabled { color: #9CA3AF; }
            QCheckBox { color: #F9FAFB; }
            QPushButton { padding: 6px 10px; border-radius: 4px; color: #F9FAFB; border: none; }
            QPushButton#TestButton { background-color: #2563EB; }
            QPushButton#ConfirmButton { background-color: #059669; }
            QPushButton#MismatchButton { background-color: #DC2626; }
            QPushButton#UpdateBitButton { background-color: #6B7280; }
            QPushButton#PatternButton { background-color: #4B5563; }
            QPushButton#CopyButton { background-color: #4B5563; }
            """
        )

        layout = QVBoxLayout()
        layout.setSpacing(14)

        # Info Group
        info_group = QGroupBox("Pixel Info")
        info_layout = QFormLayout()
        self.lbl_coords = QLabel("-")
        self.lbl_type = QLabel("-")
        self.lbl_address = QLabel("-")
        self.lbl_status = QLabel("-")

        self.lbl_bit_index = QLabel("-")

        info_layout.addRow("Coords (row,col):", self.lbl_coords)
        info_layout.addRow("Type:", self.lbl_type)
        info_layout.addRow("Address:", self.lbl_address)
        info_layout.addRow("Bit Index:", self.lbl_bit_index)
        info_layout.addRow("Status:", self.lbl_status)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Command Group
        cmd_group = CopyableGroupBox("Command", self._copy_assigned_command)
        self.command_group = cmd_group
        cmd_layout = QVBoxLayout()
        cmd_layout.setContentsMargins(12, 28, 12, 12)
        self.txt_assigned = QTextEdit()
        self.txt_assigned.setReadOnly(True)
        self.txt_assigned.setAcceptRichText(True)
        self.txt_assigned.setFixedHeight(48)
        self.txt_assigned.setLineWrapMode(QTextEdit.NoWrap)
        cmd_layout.addWidget(self.txt_assigned)
        cmd_group.setLayout(cmd_layout)
        layout.addWidget(cmd_group)
        self.btn_copy_assigned = cmd_group.copy_button
        self.btn_copy_assigned.setToolTip("Copy command")

        self.extra_group = CopyableGroupBox("Alternate Command", self._copy_alt_command)
        self.extra_group.setVisible(False)
        self.extra_group_layout = QVBoxLayout()
        self.extra_group_layout.setContentsMargins(12, 28, 12, 12)
        self.extra_group_field = QTextEdit()
        self.extra_group_field.setReadOnly(True)
        self.extra_group_field.setAcceptRichText(True)
        self.extra_group_field.setFixedHeight(48)
        self.extra_group_field.setLineWrapMode(QTextEdit.NoWrap)
        self.extra_group_layout.addWidget(self.extra_group_field)
        self.extra_group.setLayout(self.extra_group_layout)
        layout.addWidget(self.extra_group)
        self.btn_copy_alt = self.extra_group.copy_button
        self.btn_copy_alt.setToolTip("Copy alternate command")

        # Actions Group
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout()
        self.mapping_toggle = QCheckBox("Mapping")
        self.mapping_toggle.setEnabled(False)
        self.mapping_toggle.setVisible(False)
        action_layout.addWidget(self.mapping_toggle)
        self.btn_test = QPushButton("Send")
        self.btn_test.setObjectName("TestButton")
        self.btn_test.clicked.connect(self.on_test_clicked)
        self.btn_confirm = QPushButton("Confirm OK")
        self.btn_confirm.setObjectName("ConfirmButton")
        self.btn_confirm.clicked.connect(self.confirm_ok_requested.emit)
        self.btn_mismatch = QPushButton("Mark Mismatch")
        self.btn_mismatch.setObjectName("MismatchButton")
        self.btn_mismatch.clicked.connect(self.mark_mismatch_requested.emit)
        self.btn_reset = QPushButton("Clear")
        self.btn_reset.setObjectName("UpdateBitButton")
        self.btn_reset.clicked.connect(self.reset_status_requested.emit)
        action_layout.addWidget(self.btn_test)
        action_layout.addWidget(self.btn_confirm)
        action_layout.addWidget(self.btn_mismatch)
        action_layout.addWidget(self.btn_reset)
        action_group.setLayout(action_layout)
        layout.addWidget(action_group)

        pattern_group = QGroupBox("Pattern")
        pattern_layout = QVBoxLayout()
        self.pattern_status = QLabel("Pattern: OFF")
        self.btn_pattern = QPushButton("Next Pattern")
        self.btn_pattern.setObjectName("PatternButton")
        self.btn_pattern.clicked.connect(self.pattern_toggle_requested.emit)
        pattern_layout.addWidget(self.pattern_status)
        pattern_layout.addWidget(self.btn_pattern)
        pattern_group.setLayout(pattern_layout)
        layout.addWidget(pattern_group)

        layout.addStretch()
        self.setLayout(layout)

        # Disable buttons initially
        self.set_enabled(False)

    def set_enabled(self, enabled):
        self.btn_test.setEnabled(enabled)
        self.btn_confirm.setEnabled(enabled)
        self.btn_mismatch.setEnabled(enabled)
        self.txt_assigned.setEnabled(enabled)
        self.lbl_bit_index.setEnabled(enabled)
        self.btn_reset.setEnabled(enabled)
        self.extra_group.setEnabled(enabled)
        if self.mapping_toggle.isVisible():
            self.mapping_toggle.setEnabled(enabled and bool(self.current_alt_command))
        else:
            self.mapping_toggle.setEnabled(False)
        self.btn_pattern.setEnabled(True)
        self.btn_copy_assigned.setEnabled(enabled and self.btn_copy_assigned.isVisible())
        self.btn_copy_alt.setEnabled(enabled and self.btn_copy_alt.isVisible())

    def update_data(self, pixel_data):
        self.current_pixel_data = pixel_data
        if not pixel_data:
            self.lbl_coords.setText("-")
            self.lbl_type.setText("-")
            self.lbl_address.setText("-")
            self.lbl_status.setText("-")
            self.lbl_bit_index.setText("-")
            self.txt_assigned.clear()
            self.command_group.set_copy_visible(False)
            self.current_alt_command = None
            self.extra_group.setVisible(False)
            self.extra_group.set_copy_visible(False)
            self.mapping_toggle.setChecked(False)
            self.mapping_toggle.setEnabled(False)
            self.set_enabled(False)
            return

        display_col = pixel_data.col + 1
        display_row = pixel_data.row + 1
        self.lbl_coords.setText(f"({display_row}, {display_col})")
        self.lbl_type.setText(
            f"0x{pixel_data.type_code:X}" if isinstance(pixel_data.type_code, int) else str(pixel_data.type_code)
        )
        self.lbl_address.setText(
            f"0x{pixel_data.address:X}" if isinstance(pixel_data.address, int) else str(pixel_data.address)
        )
        self.lbl_status.setText(self._format_status(pixel_data.status))

        # Bit Index
        bit_idx = getattr(pixel_data, "bit_index", -1)
        if bit_idx >= 0:
            self.lbl_bit_index.setText(f"0x{bit_idx:X}")
        else:
            self.lbl_bit_index.setText("-")

        assign_hex = self._format_data(pixel_data.assigned_command)
        self.txt_assigned.setToolTip(assign_hex)
        self.txt_assigned.setHtml(self._format_data_html(pixel_data.assigned_command))
        self.command_group.set_copy_visible(bool(pixel_data.assigned_command))
        remap_cmds = getattr(pixel_data, "remap_commands", [])
        remap_active = bool(getattr(pixel_data, "remap_active", False))

        if remap_cmds:
            alt = remap_cmds[0]
            self.current_alt_command = alt
            alt_hex = self._format_data(alt.data)
            self.extra_group_field.setToolTip(alt_hex)
            self.extra_group_field.setHtml(self._format_data_html(alt.data))
            self.extra_group.setVisible(True)
            self.mapping_toggle.setVisible(True)
            self.mapping_toggle.setEnabled(True)
            self.mapping_toggle.setChecked(remap_active)
            self.extra_group.set_copy_visible(bool(alt.data))
            self.btn_copy_alt.setEnabled(bool(alt.data))
            self.extra_group.setTitle(self._format_source_title(alt))
        else:
            self.current_alt_command = None
            self.extra_group_field.clear()
            self.extra_group.setVisible(False)
            self.mapping_toggle.setChecked(False)
            self.mapping_toggle.setEnabled(False)
            self.mapping_toggle.setVisible(False)
            self.extra_group.set_copy_visible(False)
            self.btn_copy_alt.setEnabled(False)
            self.extra_group.setTitle("Alternate Command")

        self.set_enabled(True)

    def update_pattern_state(self, mode: str):
        descriptions = {
            "off": "Pattern: OFF",
            "fill": "Pattern: Fill",
            "checker": "Pattern: Checkerboard",
            "checker_inv": "Pattern: Checkerboard (inverted)",
        }
        self.pattern_status.setText(descriptions.get(mode, "Pattern: OFF"))
        self.btn_pattern.setText("Next Pattern")

        self.set_enabled(True)

    def on_test_clicked(self):
        try:
            bytes_list = self._get_command_for_send()
        except ValueError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return

        if not bytes_list:
            QMessageBox.warning(self, "Error", "Command is empty")
            return

        self.test_requested.emit(bytes_list)

    def get_assigned_command(self):
        if self.current_pixel_data:
            return list(self.current_pixel_data.assigned_command)
        return []

    def _get_command_for_send(self):
        if not self.current_pixel_data:
            raise ValueError("No pixel selected")
        if self.mapping_toggle.isChecked():
            if not self.current_alt_command:
                raise ValueError("Alternate command is not available")
            if not isinstance(self.current_alt_command.address, int) or not isinstance(
                self.current_alt_command.type_code, int
            ):
                raise ValueError("Alternate command metadata is incomplete")
            return build_full_payload(
                self.current_alt_command.address,
                self.current_alt_command.type_code,
                self.current_alt_command.data,
            )
        if not isinstance(self.current_pixel_data.address, int) or not isinstance(
            self.current_pixel_data.type_code, int
        ):
            raise ValueError("Pixel has no valid command metadata")
        return build_full_payload(
            self.current_pixel_data.address,
            self.current_pixel_data.type_code,
            self.current_pixel_data.assigned_command,
        )

    def _format_data(self, data_bytes):
        if not data_bytes:
            return ""
        return "".join(f"{b:02X}" for b in data_bytes)

    def _format_data_html(self, data_bytes):
        if not data_bytes:
            return "<span style='color:#9CA3AF;'>--</span>"
        colors = ["#F97316", "#0EA5E9", "#A855F7", "#22C55E"]
        chunks = []
        for idx, b in enumerate(data_bytes):
            color = colors[idx % len(colors)]
            chunks.append(f"<span style='color:{color};font-weight:600;'>{b:02X}</span>")
        return " ".join(chunks)

    def _format_source_title(self, alt_command):
        row = getattr(alt_command, "source_row", None)
        col = getattr(alt_command, "source_col", None)
        if row is None or col is None:
            return "Alternate Command"
        return f"Alternate Command ({row + 1},{col + 1})"

    def is_mapping_mode(self):
        return self.mapping_toggle.isChecked()

    def _format_status(self, status_code: str) -> str:
        mapping = {
            "tested_ok": "OK",
            "tested_fail": "Mismatch",
            "unknown": "Unknown",
        }
        return mapping.get(status_code, status_code.replace("_", " ").title() if status_code else "-")

    def _copy_assigned_command(self):
        if not self.current_pixel_data:
            return
        data = self.current_pixel_data.assigned_command or []
        address = self.current_pixel_data.address
        type_code = self.current_pixel_data.type_code
        if address is None or type_code is None or not data:
            QMessageBox.information(self, "Copy", "Command is empty or incomplete.")
            return
        payload = build_full_payload(address, type_code, data)
        self._copy_bytes_to_clipboard(payload, self.txt_assigned, "Pixel command copied")

    def _copy_alt_command(self):
        if not self.current_alt_command:
            return
        data = self.current_alt_command.data or []
        address = self.current_alt_command.address
        type_code = self.current_alt_command.type_code
        if address is None or type_code is None or not data:
            QMessageBox.information(self, "Copy", "Alternate command is empty or incomplete.")
            return
        payload = build_full_payload(address, type_code, data)
        self._copy_bytes_to_clipboard(payload, self.extra_group_field, "Alternate command copied")

    def _copy_bytes_to_clipboard(self, data, widget, tooltip_text):
        if not data:
            QMessageBox.information(self, "Copy", "Command is empty.")
            return
        hex_string = ",".join(f"0x{b:02X}" for b in data)
        QGuiApplication.clipboard().setText(hex_string)
        QToolTip.showText(widget.mapToGlobal(widget.rect().center()), tooltip_text, widget, widget.rect(), 800)
        self._flash_copy_feedback(widget)

    def _flash_copy_feedback(self, widget):
        effect = QGraphicsColorizeEffect(widget)
        effect.setColor(QColor("#22C55E"))
        widget.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"strength", widget)
        animation.setDuration(350)
        animation.setStartValue(0.8)
        animation.setEndValue(0.0)

        def _cleanup():
            widget.setGraphicsEffect(None)

        animation.finished.connect(_cleanup)
        animation.start(QPropertyAnimation.DeleteWhenStopped)
