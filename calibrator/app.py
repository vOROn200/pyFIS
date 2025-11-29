import sys
import logging
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from ui.main_window import MainWindow

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[logging.FileHandler("calibration.log"), logging.StreamHandler()],
)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(15, 23, 42))
    dark_palette.setColor(QPalette.WindowText, QColor(249, 250, 251))
    dark_palette.setColor(QPalette.Base, QColor(15, 23, 42))
    dark_palette.setColor(QPalette.AlternateBase, QColor(30, 41, 59))
    dark_palette.setColor(QPalette.ToolTipBase, QColor(15, 23, 42))
    dark_palette.setColor(QPalette.ToolTipText, QColor(249, 250, 251))
    dark_palette.setColor(QPalette.Text, QColor(249, 250, 251))
    dark_palette.setColor(QPalette.Button, QColor(30, 41, 59))
    dark_palette.setColor(QPalette.ButtonText, QColor(249, 250, 251))
    dark_palette.setColor(QPalette.Highlight, QColor(37, 99, 235))
    dark_palette.setColor(QPalette.HighlightedText, QColor(249, 250, 251))
    app.setPalette(dark_palette)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
