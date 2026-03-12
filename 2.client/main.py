
import os
from ui.dashboard import run_dashboard


if __name__ == "__main__":
    os.environ["QT_IM_MODULE"] = "ibus"  # 입력기 모드 설정 (KDE는 보통 fcitx, 안되면 ibus 시도)
    run_dashboard()

