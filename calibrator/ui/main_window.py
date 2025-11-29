import sys
import os
import logging
import json
from datetime import datetime
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QMessageBox, QDialog, QFileDialog
from PySide6.QtGui import QAction
from PySide6.QtCore import Slot

from backend.model import PixelData, SegmentMapping, AlternateCommand
from backend.persistence import PersistenceManager
from backend.transport import Transport
from backend.segment_logic import SegmentLogic
from backend.command_codec import extract_data_bytes, build_full_payload
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
        self.pattern_cycle = ["off", "fill", "checker", "checker_inv"]
        self.pattern_mode = "off"

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
        self._init_menus()

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
        self.detail.pattern_toggle_requested.connect(self.on_pattern_toggle)
        main_layout.addWidget(self.detail, stretch=1)
        self.detail.update_pattern_state(self.pattern_mode)

        # Refresh grid colors
        self.refresh_grid()

    def _init_menus(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")

        self.action_export_mapping = file_menu.addAction("Export mapping")
        self.action_export_mapping.triggered.connect(self.on_export_mapping)

        file_menu.addSeparator()
        self.action_quit = file_menu.addAction("Quit")
        self.action_quit.setShortcut("Ctrl+Q")
        self.action_quit.setMenuRole(QAction.MenuRole.NoRole)
        self.action_quit.triggered.connect(self.close)

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

    @Slot()
    def on_pattern_toggle(self):
        next_mode = self._next_pattern_mode()
        payloads = self._build_pattern_payloads(next_mode)
        if not payloads:
            QMessageBox.warning(self, "Error", "Unable to build blank pattern payloads.")
            return

        success = self.transport.send_payload_batch(payloads)
        if not success:
            QMessageBox.warning(self, "Error", "Failed to send pattern payloads")
            return

        self.pattern_mode = next_mode
        self.detail.update_pattern_state(self.pattern_mode)
        logger.info("Pattern mode switched to %s", self.pattern_mode)

    @Slot()
    def on_export_mapping(self):
        default_path = os.path.abspath(self.mapping_path)
        dialog_path = os.path.splitext(default_path)[0] + "-export.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Mapping",
            dialog_path,
            "JSON Files (*.json);;All Files (*)",
        )
        if not file_path:
            return

        try:
            export_payload = self._build_mapping_export()
            with open(file_path, "w", encoding="utf-8") as fp:
                json.dump(export_payload, fp, indent=2)
        except Exception as exc:
            logger.exception("Failed to export mapping: %s", exc)
            QMessageBox.warning(self, "Export Mapping", f"Failed to export mapping: {exc}")
            return

    def _next_pattern_mode(self):
        if not self.pattern_cycle:
            return "off"
        try:
            idx = self.pattern_cycle.index(self.pattern_mode)
        except ValueError:
            return self.pattern_cycle[0]
        return self.pattern_cycle[(idx + 1) % len(self.pattern_cycle)]

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

    def _build_pattern_payloads(self, mode: str):
        template = self._get_blank_payload_template()
        if not template:
            return []

        if mode == "off":
            return [list(payload) for payload in template]

        payload_buffers = [bytearray(p) for p in template]
        parity = None
        if mode == "checker":
            parity = 0
        elif mode == "checker_inv":
            parity = 1

        for pixel in self.mapping.pixels:
            if getattr(pixel, "status", "") != "tested_ok":
                continue

            if parity is not None and ((pixel.row + pixel.col) % 2 != parity):
                continue

            command_info = self._resolve_pixel_command(pixel)
            if not command_info:
                continue

            address, type_code, data_bytes = command_info
            idx = self._blank_payload_map.get(address)
            if idx is None or idx >= len(payload_buffers):
                continue

            payload = build_full_payload(address, type_code, data_bytes)
            self._merge_payload(payload_buffers[idx], payload)

        return [list(buf) for buf in payload_buffers]

    def _resolve_pixel_command(self, pixel):
        if getattr(pixel, "remap_active", False) and getattr(pixel, "remap_commands", []):
            alt = pixel.remap_commands[0]
            if alt.address is None or alt.type_code is None:
                return None
            return alt.address, alt.type_code, list(alt.data)

        if pixel.address is None or pixel.type_code is None:
            return None
        data_bytes = pixel.assigned_command or pixel.generated_command
        if not data_bytes:
            return None
        return pixel.address, pixel.type_code, list(data_bytes)

    def _build_mapping_export(self):
        export_pixels = []
        for pixel in self.mapping.pixels:
            if getattr(pixel, "status", "") != "tested_ok":
                continue

            command_info = self._resolve_pixel_command(pixel)
            if not command_info:
                continue

            address, type_code, data_bytes = command_info
            payload = build_full_payload(address, type_code, data_bytes)
            export_pixels.append(
                {
                    "row": pixel.row + 1,
                    "col": pixel.col + 1,
                    "address": f"0x{address:02X}",
                    "type": f"0x{type_code:02X}",
                    "command": ",".join(f"0x{b:02X}" for b in payload),
                }
            )

        return {
            "segment": getattr(self.mapping, "segment_name", "unknown"),
            "exported_at": datetime.utcnow().isoformat(),
            "pixels": export_pixels,
        }

    def _merge_payload(self, target_buffer: bytearray, source_payload):
        if not target_buffer or not source_payload:
            return

        if len(source_payload) > len(target_buffer):
            target_buffer.extend([0] * (len(source_payload) - len(target_buffer)))

        for idx in range(1, min(len(target_buffer), len(source_payload))):
            pos = idx - 1
            if pos % 6 == 0:
                # Type byte; trust template value
                continue
            target_buffer[idx] |= source_payload[idx]

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
