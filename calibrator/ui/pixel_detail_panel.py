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
)
from PySide6.QtCore import Signal

from backend.command_codec import build_full_payload


class PixelDetailPanel(QWidget):
    test_requested = Signal(list)  # command bytes
    confirm_ok_requested = Signal()
    mark_mismatch_requested = Signal()
    reset_status_requested = Signal()
    bit_index_changed = Signal(int)  # new bit index

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
            QPushButton { padding: 6px 10px; border-radius: 4px; color: #F9FAFB; border: none; }
            QPushButton#TestButton { background-color: #2563EB; }
            QPushButton#ConfirmButton { background-color: #059669; }
            QPushButton#MismatchButton { background-color: #DC2626; }
            QPushButton#UpdateBitButton { background-color: #6B7280; }
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

        self.txt_bit_index = QLineEdit()
        self.txt_bit_index.setMinimumWidth(55)
        self.txt_bit_index.setMaxLength(8)
        self.txt_bit_index.setReadOnly(True)

        bit_layout = QHBoxLayout()
        bit_layout.addWidget(self.txt_bit_index)

        info_layout.addRow("Coords (row,col):", self.lbl_coords)
        info_layout.addRow("Type:", self.lbl_type)
        info_layout.addRow("Address:", self.lbl_address)
        info_layout.addRow("Bit Index:", bit_layout)
        info_layout.addRow("Status:", self.lbl_status)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Command Group
        cmd_group = QGroupBox("Command")
        cmd_layout = QVBoxLayout()
        self.txt_assigned = QTextEdit()
        self.txt_assigned.setReadOnly(True)
        self.txt_assigned.setAcceptRichText(True)
        self.txt_assigned.setFixedHeight(48)
        self.txt_assigned.setLineWrapMode(QTextEdit.NoWrap)
        cmd_layout.addWidget(self.txt_assigned)
        cmd_group.setLayout(cmd_layout)
        layout.addWidget(cmd_group)

        self.extra_group = QGroupBox("Alternate Command")
        self.extra_group.setVisible(False)
        self.extra_group_layout = QVBoxLayout()
        self.extra_group_layout.setContentsMargins(8, 8, 8, 8)
        self.extra_group_field = QTextEdit()
        self.extra_group_field.setReadOnly(True)
        self.extra_group_field.setAcceptRichText(True)
        self.extra_group_field.setFixedHeight(48)
        self.extra_group_field.setLineWrapMode(QTextEdit.NoWrap)
        self.extra_group_layout.addWidget(self.extra_group_field)
        self.extra_group.setLayout(self.extra_group_layout)
        layout.addWidget(self.extra_group)

        # Actions Group
        action_group = QGroupBox("Actions")
        action_layout = QVBoxLayout()
        self.mapping_toggle = QCheckBox("Mapping")
        self.mapping_toggle.setEnabled(False)
        action_layout.addWidget(self.mapping_toggle)
        self.btn_test = QPushButton("Test (Send)")
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

        layout.addStretch()
        self.setLayout(layout)

        # Disable buttons initially
        self.set_enabled(False)

    def set_enabled(self, enabled):
        self.btn_test.setEnabled(enabled)
        self.btn_confirm.setEnabled(enabled)
        self.btn_mismatch.setEnabled(enabled)
        self.txt_assigned.setEnabled(enabled)
        self.txt_bit_index.setEnabled(enabled)
        self.btn_reset.setEnabled(enabled)
        self.extra_group.setEnabled(enabled)
        self.mapping_toggle.setEnabled(enabled and bool(self.current_alt_command))

    def update_data(self, pixel_data):
        self.current_pixel_data = pixel_data
        if not pixel_data:
            self.lbl_coords.setText("-")
            self.lbl_type.setText("-")
            self.lbl_address.setText("-")
            self.lbl_status.setText("-")
            self.txt_bit_index.setText("")
            self.txt_assigned.clear()
            self.current_alt_command = None
            self.extra_group.setVisible(False)
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
        self.lbl_status.setText(pixel_data.status)

        # Bit Index
        bit_idx = getattr(pixel_data, "bit_index", -1)
        if bit_idx >= 0:
            self.txt_bit_index.setText(f"0x{bit_idx:X}")
        else:
            self.txt_bit_index.setText("-")

        assign_hex = self._format_data(pixel_data.assigned_command)
        self.txt_assigned.setToolTip(assign_hex)
        self.txt_assigned.setHtml(self._format_data_html(pixel_data.assigned_command))
        remap_cmds = getattr(pixel_data, "remap_commands", [])
        remap_active = bool(getattr(pixel_data, "remap_active", False))

        if remap_cmds:
            alt = remap_cmds[0]
            self.current_alt_command = alt
            alt_hex = self._format_data(alt.data)
            self.extra_group_field.setToolTip(alt_hex)
            self.extra_group_field.setHtml(self._format_data_html(alt.data))
            self.extra_group.setVisible(True)
            self.mapping_toggle.setEnabled(True)
            self.mapping_toggle.setChecked(remap_active)
            self.extra_group.setTitle(self._format_source_title(alt))
        else:
            self.current_alt_command = None
            self.extra_group_field.clear()
            self.extra_group.setVisible(False)
            self.mapping_toggle.setChecked(False)
            self.mapping_toggle.setEnabled(False)
            self.extra_group.setTitle("Alternate Command")

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
