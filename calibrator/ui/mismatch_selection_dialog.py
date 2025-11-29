from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt

from ui.pixel_grid_widget import PixelGridWidget


class MismatchSelectionDialog(QDialog):
    """Modal dialog that lets the user choose the pixel that actually lit up."""

    def __init__(self, mapping, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Actual Pixel")
        self.setModal(True)
        self.resize(860, 520)

        self.mapping = mapping
        self.selected_coords = None

        self._init_ui()
        self._populate_grid()

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(12)

        info_label = QLabel(
            "Choose the pixel on the calibration grid that actually lit up.\n"
            "The current pixel command will be stored as an alternate for that pixel."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        self.grid = PixelGridWidget(rows=13, cols=24)
        self.grid.pixel_clicked.connect(self.on_pixel_clicked)
        layout.addWidget(self.grid, stretch=1)

        self.selection_label = QLabel("No pixel selected")
        layout.addWidget(self.selection_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch(1)

        self.btn_select = QPushButton("Assign")
        self.btn_select.setEnabled(False)
        self.btn_select.clicked.connect(self._on_confirm)
        self.btn_select.setStyleSheet(
            "QPushButton { background-color: #059669; color: #F9FAFB; padding: 6px 18px; border: none; border-radius: 4px; }"
            "QPushButton:disabled { background-color: #1F2937; color: #6B7280; }"
        )
        buttons_layout.addWidget(self.btn_select)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        buttons_layout.addWidget(btn_cancel)

        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def _populate_grid(self):
        if not self.mapping:
            return
        for pixel in self.mapping.pixels:
            has_remap = bool(getattr(pixel, "remap_commands", [])) and not getattr(pixel, "remap_active", False)
            self.grid.update_pixel_status(pixel.row, pixel.col, pixel.status, pixel.type_code, has_remap)

    def on_pixel_clicked(self, row, col):
        self.selected_coords = (row, col)
        display_row = row + 1
        display_col = col + 1
        self.selection_label.setText(f"Selected: column {display_col}, row {display_row}")
        self.grid.set_selection(row, col)
        self.btn_select.setEnabled(True)

    def _on_confirm(self):
        if self.selected_coords is None:
            return
        self.accept()

    def get_selected_coords(self):
        return self.selected_coords
