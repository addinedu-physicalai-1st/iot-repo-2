from PyQt6.QtWidgets import QApplication, QMainWindow, QTabWidget

from esp32_camera_device_esp32_cam_client import CamApp555
from esp32_board1_device_esp32_wifi_IR_RFID_Motor_Server import IntegratedApp


class DeviceTestTabsWindow(QMainWindow):
    """
    ESP32 카메라 / IR·RFID·모터 테스트용 탭 윈도우.

    - 탭 1: 기존 ESP32-CAM 테스트 UI
    - 탭 2: 기존 IR/RFID/Motor 테스트 UI
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Device Test Tabs - ESP32 Camera / IR-RFID-Motor")
        self.resize(1200, 800)

        tabs = QTabWidget()
        self.setCentralWidget(tabs)

        self.cam_widget = CamApp555()
        self.ir_rfid_widget = IntegratedApp()

        tabs.addTab(self.cam_widget, "ESP32-CAM")
        tabs.addTab(self.ir_rfid_widget, "ESP32 IR/RFID/Motor")


def main() -> None:
    import sys

    app = QApplication(sys.argv)
    win = DeviceTestTabsWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

