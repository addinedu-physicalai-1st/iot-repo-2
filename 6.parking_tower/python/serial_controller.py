import time

try:
    import serial
except ImportError:
    serial = None


class ArduinoClient:
    def __init__(self, port: str = "/dev/ttyACM0", baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.mock = False
        self.last_status = {
            "homed": 0,
            "moving": 0,
            "emergency": 0,
            "full": 0,
            "allowIn": 1,
            "plate": 0,
            "sensor": 0,
            "stepPos": 0,
        }

        if serial is None:
            self.mock = True
            return

        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.2)
            time.sleep(2)
        except Exception:
            self.mock = True

    def send(self, cmd: str):
        if self.mock:
            lines = self._mock_send(cmd)
            self._parse_status_lines(lines)
            return lines

        lines = []
        try:
            self.ser.write((cmd + "\n").encode())
            time.sleep(0.15)
            end_time = time.time() + 1.2
            while time.time() < end_time:
                line = self.ser.readline().decode(errors="ignore").strip()
                if line:
                    lines.append(line)
        except Exception as e:
            lines.append(f"ERR|SERIAL|{e}")
        self._parse_status_lines(lines)
        return lines

    def _parse_status_lines(self, lines):
        for line in lines:
            if line.startswith("STATUS|"):
                parts = line.split("|")[1:]
                for part in parts:
                    if "=" in part:
                        k, v = part.split("=", 1)
                        try:
                            self.last_status[k] = int(v)
                        except ValueError:
                            self.last_status[k] = v

    def _mock_send(self, cmd: str):
        cmd = cmd.strip()
        if cmd == "PING":
            return ["OK|PONG"]
        if cmd == "HOME":
            self.last_status["homed"] = 1
            self.last_status["plate"] = 0
            self.last_status["sensor"] = 1
            return ["OK|HOME_DONE", self._mock_status_line()]
        if cmd == "STATUS":
            return [self._mock_status_line()]
        if cmd == "EMG_ON":
            self.last_status["emergency"] = 1
            self.last_status["moving"] = 0
            return ["OK|EMG_ON", self._mock_status_line()]
        if cmd == "EMG_OFF":
            self.last_status["emergency"] = 0
            return ["OK|EMG_OFF", self._mock_status_line()]
        if cmd.startswith("FULL="):
            self.last_status["full"] = int(cmd.split("=")[1])
            return ["OK|FULL_SET", self._mock_status_line()]
        if cmd.startswith("ALLOW_IN="):
            self.last_status["allowIn"] = int(cmd.split("=")[1])
            return ["OK|ALLOW_IN_SET", self._mock_status_line()]
        if cmd.startswith("SET_STEPS="):
            return ["OK|STEPS_UPDATED", self._mock_status_line()]
        if cmd.startswith("MOVE="):
            idx = int(cmd.split("=")[1])
            self.last_status["moving"] = 1
            self.last_status["plate"] = idx
            self.last_status["sensor"] = 1 if idx == 0 else 0
            self.last_status["moving"] = 0
            return [f"OK|MOVE_DONE|plate={idx}", self._mock_status_line()]
        return ["ERR|UNKNOWN_COMMAND"]

    def _mock_status_line(self):
        s = self.last_status
        return (
            f"STATUS|homed={s['homed']}|moving={s['moving']}|emergency={s['emergency']}|"
            f"full={s['full']}|allowIn={s['allowIn']}|plate={s['plate']}|sensor={s['sensor']}|stepPos={s['stepPos']}"
        )
