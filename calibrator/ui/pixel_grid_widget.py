from PySide6.QtWidgets import QWidget, QGridLayout, QPushButton
from PySide6.QtCore import Signal


class PixelGridWidget(QWidget):
    pixel_clicked = Signal(int, int)  # row, col

    def __init__(self, rows=13, cols=24):
        super().__init__()
        self.setObjectName("PixelGridWidget")
        self.rows = rows
        self.cols = cols
        self.buttons = {}  # (r,c) -> QPushButton
        self.pixel_states = {}  # (r,c) -> (status, ptype, has_remap)
        self._selection = None
        self.init_ui()

    def init_ui(self):
        layout = QGridLayout()
        layout.setSpacing(1)
        layout.setContentsMargins(0, 0, 0, 0)

        for r in range(self.rows):
            for c in range(self.cols):
                btn = QPushButton()
                btn.setFixedSize(30, 30)
                display_row = r + 1
                display_col = c + 1
                btn.setToolTip(f"({display_col}, {display_row})")
                btn.setAccessibleName(f"Pixel column {display_col} row {display_row}")
                btn.setStyleSheet(
                    "background-color: #1F2937; border: 1px solid #374151; border-radius: 4px; color: #F9FAFB;"
                )
                # Use a closure to capture r, c
                btn.clicked.connect(lambda checked=False, r=r, c=c: self._handle_button_click(r, c))

                layout.addWidget(btn, r, c)
                self.buttons[(r, c)] = btn

        self.setLayout(layout)
        self.setStyleSheet(
            """
            QWidget#PixelGridWidget { background-color: #0F172A; border-radius: 8px; padding: 4px; }
            """
        )

    def update_pixel_status(self, row, col, status, ptype, has_remap=False):
        if (row, col) not in self.buttons:
            return

        self.pixel_states[(row, col)] = (status, ptype, has_remap)
        self._apply_style(row, col, status, ptype, has_remap)

    def set_selection(self, row=None, col=None):
        previous = self._selection
        if previous and previous in self.pixel_states:
            prev_row, prev_col = previous
            status, ptype, has_remap = self.pixel_states.get(previous, ("unknown", 0, False))
            self._apply_style(prev_row, prev_col, status, ptype, has_remap, selected=False)

        if row is None or col is None:
            self._selection = None
            return

        self._selection = (row, col)
        status, ptype, has_remap = self.pixel_states.get((row, col), ("unknown", 0, False))
        self._apply_style(row, col, status, ptype, has_remap, selected=True)

    def _handle_button_click(self, row, col):
        self.set_selection(row, col)
        self.pixel_clicked.emit(row, col)

    def _apply_style(self, row, col, status, ptype, has_remap, selected=None):
        btn = self.buttons.get((row, col))
        if not btn:
            return

        base_color = "#E0E0E0"
        border = "1px solid #999"
        text_color = "#111827"
        indicator = ""
        font_size = "12px"

        if ptype == 0x90:
            base_color = "#FFF9C4"
        elif ptype == 0x10:
            base_color = "#B3E5FC"
        elif ptype == "hole":
            base_color = "#444444"

        color = base_color

        if status == "tested_ok":
            color = "#A5D6A7"
            border = "2px solid #2E7D32"
        elif status == "tested_fail":
            color = "#EF9A9A"
            border = "2px solid #C62828"

        if has_remap:
            indicator = "M"
            text_color = "#F97316"
            border = "2px solid #F59E0B"
            font_size = "18px"

        if selected is None:
            selected = self._selection == (row, col)

        if selected:
            border = "2px solid #FBBF24"

        btn.setStyleSheet(
            f"background-color: {color}; border: {border}; border-radius: 4px; color: {text_color}; "
            f"font-weight: 600; padding-right: 4px; padding-bottom: 2px; font-size: {font_size};"
        )
        btn.setText(indicator)
