import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from ui.main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    icon_path = Path(__file__).resolve().parent / "assets" / "mp3_studio.ico"
    app.setWindowIcon(QIcon(str(icon_path)))
    app.setApplicationName("MP3 Studio")
    app.setOrganizationName("MP3 Studio")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
