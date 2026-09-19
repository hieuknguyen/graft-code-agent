import sys
import os
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from desktop.main_window import MainWindow

def run_desktop(folder: str = None):
    # Enable high DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Graft Code Agent")
    app.setOrganizationName("Antigravity")

    window = MainWindow(initial_dir=folder)
    window.show()
    return app.exec()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Graft Code Agent - Desktop Studio")
    parser.add_argument("--dir", type=str, default=None, help="Thư mục dự án khởi tạo")
    args = parser.parse_args()

    sys.exit(run_desktop(args.dir))
