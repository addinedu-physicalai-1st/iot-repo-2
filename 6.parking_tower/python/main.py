import sys
import os
from PyQt6.QtWidgets import QApplication
from ui_main import MainWindow

if __name__ == "__main__":
    os.environ["QT_IM_MODULE"] = "ibus"  # 입력기 모드 설정 (KDE는 보통 fcitx, 안되면 ibus 시도)
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
