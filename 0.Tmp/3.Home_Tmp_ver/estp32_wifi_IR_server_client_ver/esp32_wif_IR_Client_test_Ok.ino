// ESP32 IR/조도/RFID/게이트 테스트 클라이언트 — Total_test 구조 + WiFi 서버 연동
// 서버에 ENTRY/EXIT/RFID/GATE_OPEN/GATE_CLOSED 이벤트 전송, 서버 명령으로 게이트 열기 테스트 가능

#include <Wire.h>
#include <SparkFun_APDS9960.h>
#include <ESP32Servo.h>
#include <SPI.h>
#include <MFRC522.h>
#include <WiFi.h>

#if 1 // Debug Home Mode
const char* ssid = "iptime_WiFiCE6D";
const char* password = "!Tony6251@";
const char* serverIP = "192.168.25.35";
#else
const char* ssid = "addinedu_201class_2-2.4G";
const char* password = "201class2!";
const char* serverIP = "192.168.25.5";
#endif

const uint16_t serverPort = 8080;
const unsigned long RECONNECT_INTERVAL_MS = 5000;
const unsigned long PING_INTERVAL_MS = 5000;
const unsigned long PONG_TIMEOUT_MS = 5000;

#define PING_MODE 0xFE
#define PONG_MODE 0xFD
#define MODE_EVENT      0  // 클라이언트 → 서버 이벤트
#define MODE_CMD_OPEN   2  // 서버 → 클라이언트 게이트 열기
#define EV_ENTRY       1
#define EV_EXIT        2
#define EV_RFID        3
#define EV_GATE_OPEN   4
#define EV_GATE_CLOSED 5

WiFiClient client;
unsigned long lastKeepAliveTime = 0;

#pragma pack(push, 1)
struct IRGatePacket {
    uint8_t mode;
    uint8_t event_type;
    char source[16];
    char extra[15];
};
#pragma pack(pop)

IRGatePacket txPacket;
IRGatePacket rxPacket;

// Total_test 하드웨어
SparkFun_APDS9960 apds1 = SparkFun_APDS9960();
SparkFun_APDS9960 apds2 = SparkFun_APDS9960();
Servo myServo;
MFRC522 rfid(5, 22);
TwoWire WirePort2 = TwoWire(1);

const uint16_t LIGHT_THRESHOLD = 10;
bool isGateOpen = false;

void sendEvent(uint8_t ev, const char* src, const char* ext) {
    if (!client.connected()) return;
    memset(&txPacket, 0, sizeof(txPacket));
    txPacket.mode = MODE_EVENT;
    txPacket.event_type = ev;
    strncpy(txPacket.source, src, 15);
    if (ext) strncpy(txPacket.extra, ext, 14);
    client.write((uint8_t*)&txPacket, sizeof(IRGatePacket));
}

void openGate(const char* source) {
    if (!isGateOpen) {
        isGateOpen = true;
        sendEvent(EV_GATE_OPEN, source, "");
        Serial.println("ACTION:GATE_OPEN_" + String(source));
        myServo.write(90);
        delay(3000);
        myServo.write(0);
        isGateOpen = false;
        sendEvent(EV_GATE_CLOSED, "GATE", "");
        Serial.println("ACTION:GATE_CLOSED");
    }
}

uint16_t readLightFromWire1() {
    uint16_t l = 0, h = 0;
    WirePort2.beginTransmission(0x39);
    WirePort2.write(0x94);
    if (WirePort2.endTransmission() != 0) return 0;
    WirePort2.requestFrom(0x39, 2);
    if (WirePort2.available() == 2) {
        l = WirePort2.read();
        h = WirePort2.read();
    }
    return (h << 8) | l;
}

void setup() {
    Serial.begin(115200);
    SPI.begin();
    rfid.PCD_Init();

    myServo.setPeriodHertz(50);
    myServo.attach(13, 500, 2400);
    myServo.write(0);

    Wire.begin(32, 14);
    if (apds1.init()) {
        apds1.enableLightSensor(false);
        Serial.println("Sensor 1 (Entry) Ready");
    }

    WirePort2.begin(25, 26, 100000);
    if (apds2.init()) {
        apds2.enableLightSensor(false);
        Serial.println("Sensor 2 (Exit) Ready");
    }

    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) delay(500);
    Serial.println("--- IR/Gate Client + WiFi ---");
}

unsigned long lastDetectionTime = 0;
const unsigned long DETECTION_DELAY = 1000; // 감지 후 2초간 재감지 방지

void loop() {
    if (!client.connected()) {
        client.stop();
        if (!client.connect(serverIP, serverPort)) {
            Serial.println("[Client] 서버 연결 실패. 5초 후 재시도...");
            delay(RECONNECT_INTERVAL_MS);
            return;
        }
        lastKeepAliveTime = millis();
        Serial.println("[Client] to [serverIP:" + String(serverIP) + "] 접속되었습니다.");
        delay(300);
    }

    // Keep-alive
    if (client.connected() && (millis() - lastKeepAliveTime >= PING_INTERVAL_MS)) {
        while (client.available() >= sizeof(IRGatePacket))
            client.read((uint8_t*)&rxPacket, sizeof(IRGatePacket));
        memset(&txPacket, 0, sizeof(txPacket));
        txPacket.mode = PING_MODE;
        if (client.write((uint8_t*)&txPacket, sizeof(IRGatePacket)) != sizeof(IRGatePacket)) {
            client.stop();
            return;
        }
        client.setTimeout(PONG_TIMEOUT_MS);
        size_t total = 0;
        unsigned long deadline = millis() + PONG_TIMEOUT_MS;
        while (total < sizeof(IRGatePacket) && millis() < deadline) {
            if (client.available() > 0) {
                size_t n = client.read((uint8_t*)&rxPacket + total, sizeof(IRGatePacket) - total);
                total += n;
            } else {
                delay(10);
            }
        }
        client.setTimeout(0);
        if (total != sizeof(IRGatePacket) || rxPacket.mode != PONG_MODE) {
            Serial.println("[Client] Keep-alive 응답 없음. 연결을 끊고 재시도합니다.");
            client.stop();
            return;
        }
        lastKeepAliveTime = millis();
    }

    // 서버 명령 수신 (게이트 열기 테스트)
    if (client.available() >= sizeof(IRGatePacket)) {
        client.read((uint8_t*)&rxPacket, sizeof(IRGatePacket));
        if (rxPacket.mode == MODE_CMD_OPEN) {
            Serial.println("[Client] 서버 명령: 게이트 열기");
            openGate("SERVER");
        }
    }

    // 3. 센서 감지 (쿨타임 적용)
    if (millis() - lastDetectionTime > DETECTION_DELAY) {
        uint16_t light1 = 0, light2 = 0;

        // Sensor 1 (Entry)
        if (apds1.readAmbientLight(light1)) {
            // 0이 들어오는 경우를 대비해 0보다 크고 임계값보다 낮은지 확인
            if (light1 > 0 && light1 <= LIGHT_THRESHOLD) {
                char buf[16];
                snprintf(buf, sizeof(buf), "L:%d", light1);
                sendEvent(EV_ENTRY, "ENTRY", buf);
                Serial.printf("ENTRY_DETECTED (Light: %d)\n", light1);
                lastDetectionTime = millis(); // 쿨타임 시작
            }
        }

        // Sensor 2 (Exit)
        light2 = readLightFromWire1();
        if (light2 > 0 && light2 <= LIGHT_THRESHOLD) {
            char buf[16];
            snprintf(buf, sizeof(buf), "L:%d", light2);
            sendEvent(EV_EXIT, "EXIT", buf);
            Serial.printf("EXIT_DETECTED (Light: %d)\n", light2);
            lastDetectionTime = millis(); // 쿨타임 시작
        }

    }

    // ----- 조도·RFID 감지 시 이벤트만 서버로 전송. 게이트는 서버 명령 시에만 동작 -----

    /*
    uint16_t light1 = 0, light2 = 0;

    if (apds1.readAmbientLight(light1) && light1 <= LIGHT_THRESHOLD) {
        char buf[16];
        snprintf(buf, sizeof(buf), "Light:%d", light1);
        sendEvent(EV_ENTRY, "ENTRY", buf);
        Serial.printf("ENTRY_DETECTED (Light: %d)\n", light1);
    }

    light2 = readLightFromWire1();
    if (light2 > 0 && light2 <= LIGHT_THRESHOLD) {
        char buf[16];
        snprintf(buf, sizeof(buf), "Light:%d", light2);
        sendEvent(EV_EXIT, "EXIT", buf);
        Serial.printf("EXIT_DETECTED (Light: %d)\n", light2);
    }
    */

    
    /*
    if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
        sendEvent(EV_RFID, "RFID", "");
        Serial.println("RFID_ALLOWED");
        rfid.PICC_HaltA();
        rfid.PCD_StopCrypto1();
    }*/
    

    delay(150);
}
