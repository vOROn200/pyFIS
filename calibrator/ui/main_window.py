import sys
import os
import logging
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QMessageBox, QDialog
from PySide6.QtCore import Slot

from backend.model import PixelData, SegmentMapping, AlternateCommand
from backend.persistence import PersistenceManager
from backend.transport import Transport
from backend.segment_logic import SegmentLogic
from backend.command_codec import extract_data_bytes
from ui.pixel_grid_widget import PixelGridWidget
from ui.pixel_detail_panel import PixelDetailPanel
from ui.mismatch_selection_dialog import MismatchSelectionDialog

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LAWO Segment Calibrator")
        self.resize(1000, 600)

        # Core components
        # Determine config path relative to this file (ui/main_window.py -> ../config.json)
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "config.json")

        self.persistence = PersistenceManager(config_path=config_path)
        self.config = self.persistence.config
        self.frame_format = self.config.get("frame_format", "raw-payload")
        self.logic = SegmentLogic(display_address=int(self.config.get("display_address", 0x05)))
        self._blank_payload_template = None
        self._blank_payload_map = {}

        self.transport = Transport(
            port=self.config.get("serial_port", "COM1"),
            baudrate=self.config.get("baudrate", 19200),
            simulation=False,  # Can be toggled
            display_address=int(self.config.get("display_address", 0x05)),
            pre_width=int(self.config.get("pre_bitmap_width", 0x08)),
            pre_height=int(self.config.get("pre_bitmap_height", 0x04)),
            command_delay=float(self.config.get("command_delay_seconds", 0.2)),
        )

        # Load mapping
        self.mapping_path = self.config.get("mapping_file_path", "mapping.json")
        self.mapping = self.persistence.load_mapping(self.mapping_path)

        if not self.mapping:
            self.init_new_mapping()

        self.current_pixel = None  # (row, col)

        self.init_ui()
        self.connect_transport()

    def init_new_mapping(self):
        seg_name = self.config.get("segment_name", "top-left")
        self.mapping = SegmentMapping(segment_name=seg_name)

        # Populate pixels
        # Assuming 13x24
        for r in range(13):
            for c in range(24):
                info = self.logic.get_pixel_info(seg_name, r, c)
                cmd = self.logic.generate_single_pixel_command(seg_name, r, c, self.frame_format)
                compact_cmd = extract_data_bytes(cmd)

                pixel = PixelData(
                    row=r,
                    col=c,
                    type_code=info.get("type", 0),
                    address=info.get("address", 0),
                    bit_index=info.get("bit_index", -1),
                    generated_command=compact_cmd,
                    assigned_command=list(compact_cmd),
                    status="unknown",
                )
                self.mapping.pixels.append(pixel)

        self.persistence.save_mapping(self.mapping_path, self.mapping)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)

        # Left: Grid
        self.grid = PixelGridWidget(rows=13, cols=24)
        self.grid.pixel_clicked.connect(self.on_pixel_selected)
        main_layout.addWidget(self.grid, stretch=2)

        # Right: Detail
        self.detail = PixelDetailPanel()
        self.detail.test_requested.connect(self.on_test_command)
        self.detail.confirm_ok_requested.connect(self.on_confirm_ok)
        self.detail.mark_mismatch_requested.connect(self.on_mark_mismatch)
        self.detail.reset_status_requested.connect(self.on_reset_status)
        self.detail.bit_index_changed.connect(self.on_bit_index_changed)
        main_layout.addWidget(self.detail, stretch=1)

        # Refresh grid colors
        self.refresh_grid()

    def connect_transport(self):
        try:
            self.transport.connect()
        except Exception as e:
            QMessageBox.warning(
                self, "Connection Error", f"Could not connect to serial port: {e}\nSwitching to simulation."
            )
            self.transport.simulation = True

    def get_pixel_data(self, r, c):
        for p in self.mapping.pixels:
            if p.row == r and p.col == c:
                return p
        return None

    def refresh_grid(self):
        for p in self.mapping.pixels:
            has_remap = bool(getattr(p, "remap_commands", [])) and not getattr(p, "remap_active", False)
            self.grid.update_pixel_status(p.row, p.col, p.status, p.type_code, has_remap)
        if self.current_pixel:
            self.grid.set_selection(*self.current_pixel)

    @Slot(int, int)
    def on_pixel_selected(self, r, c):
        self.current_pixel = (r, c)
        p = self.get_pixel_data(r, c)
        self.detail.update_data(p)

    @Slot(list)
    def on_test_command(self, cmd_bytes):
        if self.config.get("send_clear_before_test", False):
            # Send clear command (TODO: implement clear command in transport or logic)
            pass

        payload_batch = self._compose_full_matrix_payloads(cmd_bytes)
        if not payload_batch:
            QMessageBox.warning(self, "Error", "Unable to build payload batch")
            return

        success = self.transport.send_payload_batch(payload_batch)
        if success:
            logger.info(f"Sent command for pixel {self.current_pixel}")
            updated = False
            p = None
            if self.current_pixel:
                p = self.get_pixel_data(*self.current_pixel)
                if p and self.detail.is_mapping_mode() and getattr(p, "remap_commands", []):
                    if not getattr(p, "remap_active", False):
                        p.remap_active = True
                        updated = True
                elif p and not self.detail.is_mapping_mode() and getattr(p, "remap_active", False):
                    # Sending default command does not change mapping state
                    updated = False
            if updated:
                self.save_state()
                self.refresh_grid()
                self.detail.update_data(p)
        else:
            QMessageBox.warning(self, "Error", "Failed to send command")

    @Slot()
    def on_confirm_ok(self):
        if not self.current_pixel:
            return
        r, c = self.current_pixel
        p = self.get_pixel_data(r, c)
        if p:
            p.status = "tested_ok"
            # Update assigned command from UI just in case
            p.assigned_command = self.detail.get_assigned_command()
            self.save_state()
            self.refresh_grid()
            self.detail.update_data(p)

    @Slot()
    def on_mark_mismatch(self):
        if not self.current_pixel:
            return
        r, c = self.current_pixel
        p = self.get_pixel_data(r, c)
        if not p:
            return

        dialog = MismatchSelectionDialog(self.mapping, self)
        result = dialog.exec()
        if result != QDialog.Accepted:
            return

        selected = dialog.get_selected_coords()
        if not selected:
            return

        target = self.get_pixel_data(*selected)
        if not target:
            QMessageBox.warning(self, "Error", "Unable to locate the selected pixel in the current mapping.")
            return

        current_command = self.detail.get_assigned_command()
        if not current_command:
            QMessageBox.warning(self, "Error", "Current pixel command is not defined.")
            return

        alt_command = AlternateCommand(
            address=p.address,
            type_code=p.type_code,
            data=list(current_command),
            source_row=p.row,
            source_col=p.col,
        )
        target.remap_commands = [alt_command]
        target.remap_active = False

        p.status = "tested_fail"
        p.assigned_command = current_command

        self.save_state()
        self.refresh_grid()
        self.detail.update_data(p)

    @Slot()
    def on_reset_status(self):
        if not self.current_pixel:
            return
        r, c = self.current_pixel
        p = self.get_pixel_data(r, c)
        if p:
            p.status = "unknown"
            p.assigned_command = list(p.generated_command)
            p.remap_commands = []
            p.remap_active = False
            self.save_state()
            self.refresh_grid()
            self.detail.update_data(p)

    @Slot(int)
    def on_bit_index_changed(self, new_index):
        if not self.current_pixel:
            return
        r, c = self.current_pixel
        p = self.get_pixel_data(r, c)
        if p:
            p.bit_index = new_index

            # Regenerate command from bit index
            seg_name = self.mapping.segment_name
            cmd = self.logic.generate_command_from_bit_index(
                seg_name, p.address, p.type_code, new_index, self.frame_format
            )

            compact = extract_data_bytes(cmd)
            p.generated_command = compact
            p.assigned_command = list(compact)  # Auto-update assigned when bit index changes manually

            self.save_state()
            self.detail.update_data(p)
            logger.info(f"Updated pixel ({r},{c}) bit_index to {new_index}")

    def _compose_full_matrix_payloads(self, active_payload):
        template = self._get_blank_payload_template()
        if not template:
            return [list(active_payload)] if active_payload else []

        payloads = [list(payload) for payload in template]
        if not active_payload:
            return payloads

        addr = active_payload[0]
        idx = self._blank_payload_map.get(addr)
        if idx is not None:
            payloads[idx] = list(active_payload)
        else:
            payloads.insert(0, list(active_payload))
        return payloads

    def _get_blank_payload_template(self):
        if self._blank_payload_template is None:
            payloads = self.logic.generate_blank_payloads("raw-payload")
            self._blank_payload_template = payloads
            self._blank_payload_map = {}
            for index, payload in enumerate(payloads):
                if payload:
                    self._blank_payload_map[payload[0]] = index
        return self._blank_payload_template

    def save_state(self):
        self.persistence.save_mapping(self.mapping_path, self.mapping)

    def closeEvent(self, event):
        self.transport.close()
        event.accept()
