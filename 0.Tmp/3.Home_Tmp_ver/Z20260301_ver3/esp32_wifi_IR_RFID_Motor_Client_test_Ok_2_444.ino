#include <Wire.h>
#include <SparkFun_APDS9960.h>
#include <ESP32Servo.h>
#include <SPI.h>
#include <MFRC522.h>
#include <WiFi.h>

// [설정] 네트워크 환경
const char* ssid = "iptime_WiFiCE6D";
const char* password = "!Tony6251@";
const char* serverIP = "192.168.25.35";
const uint16_t serverPort = 8080;

// [안정화 설정]
const int INIT_SLEEP_MS = 3000;
const int MAX_RETRY = 5;

// 패킷 타입 (4=장비목록 전송)
#define TYPE_PING        0xFE
#define TYPE_PONG        0xFD
#define TYPE_IR_EVENT    0
#define TYPE_RFID        1
#define TYPE_CMD_OPEN    2
#define TYPE_CMD_CLOSE   5   // 서버 → 클라이언트: 게이트 닫기
#define TYPE_CMD_WRITE   3
#define TYPE_DEVICE_LIST 4   // 접속 시 서버로 장비 목록(GUID, 센서명) 전송

#define EV_ENTRY         1
#define EV_EXIT          2
#define EV_RFID          3
#define EV_GATE_OPEN     4
#define EV_GATE_CLOSED   5
#define EV_ERROR         99

#pragma pack(push, 1)
struct UnifiedPacket {
    uint8_t type;
    uint8_t payload[32];
};
#pragma pack(pop)

WiFiClient client;
UnifiedPacket txPkt;
UnifiedPacket rxPkt;

TwoWire WirePort2 = TwoWire(1);
SparkFun_APDS9960 apds = SparkFun_APDS9960();
SparkFun_APDS9960 apds1 = SparkFun_APDS9960();
SparkFun_APDS9960 apds2 = SparkFun_APDS9960();
Servo myServo;
MFRC522 rfid(5, 22);
MFRC522::MIFARE_Key key;

const uint16_t LIGHT_THRESHOLD = 10;
const int RFID_BLOCK = 4;
bool isGateOpen = false;
bool serverWriteSiteID = false;
char serverSiteID[16] = {0};

bool sensor1_ok = false;
bool sensor2_ok = false;
unsigned long lastKeepAliveTime = 0;
unsigned long lastDetectionTime = 0;
const unsigned long DETECTION_DELAY = 1000;
const unsigned long PING_INTERVAL_MS = 5000;
const unsigned long PONG_TIMEOUT_MS = 5000;

#define I2C_SDA1 32
#define I2C_SCL1 14
#define I2C_SDA2 25
#define I2C_SCL2 26

// 센서별 GUID(16자) + 영문 센서명(14자). 접속 시 서버 전송 → DB/리스트 연동
#define DEVICE_COUNT 4
static const struct { const char guid[17]; const char name[15]; } DEVICE_LIST[DEVICE_COUNT] = {
    { "ESP32-S1-ENTRY01", "EntryVehDetect" },  // 입구 차량 감지
    { "ESP32-S2-EXIT01 ", "ExitVehDetect" },   // 출구 차량 감지
    { "ESP32-RFID-01   ", "RFIDReader" },
    { "ESP32-GATE-01   ", "GateServo" },
};
bool deviceListSent = false;

void sendDeviceList() {
    if (!client.connected()) return;
    for (uint8_t i = 0; i < DEVICE_COUNT; i++) {
        memset(&txPkt, 0, sizeof(txPkt));
        txPkt.type = TYPE_DEVICE_LIST;
        txPkt.payload[0] = i;
        txPkt.payload[1] = DEVICE_COUNT;
        strncpy((char*)&txPkt.payload[2], DEVICE_LIST[i].guid, 16);
        strncpy((char*)&txPkt.payload[18], DEVICE_LIST[i].name, 14);
        client.write((uint8_t*)&txPkt, sizeof(UnifiedPacket));
        delay(20);
    }
    Serial.println("Device list sent to server.");
}

void sendEvent(uint8_t ev, const char* src, const char* ext) {
    if (!client.connected()) return;
    memset(&txPkt, 0, sizeof(txPkt));
    txPkt.type = TYPE_IR_EVENT;
    txPkt.payload[0] = ev;
    strncpy((char*)&txPkt.payload[1], src, 15);
    if (ext) strncpy((char*)&txPkt.payload[17], ext, 14);
    client.write((uint8_t*)&txPkt, sizeof(UnifiedPacket));
}

void sendRFID(uint8_t mode, const char* uid, const char* siteid) {
    if (!client.connected()) return;
    memset(&txPkt, 0, sizeof(txPkt));
    txPkt.type = TYPE_RFID;
    txPkt.payload[0] = mode;
    strncpy((char*)&txPkt.payload[1], uid, 15);
    strncpy((char*)&txPkt.payload[17], siteid, 14);
    client.write((uint8_t*)&txPkt, sizeof(UnifiedPacket));
}

// 서버 명령(TYPE_CMD_OPEN) 수신 시에만 호출. 입구/출구/RFID 감지 시에는 호출하지 않음.
void openGate(const char* source) {
    if (!isGateOpen) {
        isGateOpen = true;
        sendEvent(EV_GATE_OPEN, source, "");
        Serial.println("ACTION: GATE_OPEN BY " + String(source));
        myServo.write(90);
    }
}

// 서버 명령(TYPE_CMD_CLOSE) 수신 시에만 호출.
void closeGate(const char* source) {
    if (isGateOpen) {
        myServo.write(0);
        isGateOpen = false;
        sendEvent(EV_GATE_CLOSED, source, "");
        Serial.println("ACTION: GATE_CLOSED BY " + String(source));
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
    Serial.println("Init setup : Start (333 - device list)");
    delay(5000);

    Wire.begin(I2C_SDA1, I2C_SCL1);
    delay(500);
    for (int i = 0; i < MAX_RETRY; i++) {
        if (apds1.init() && apds1.enableLightSensor(false)) { sensor1_ok = true; break; }
        delay(500);
    }

    delay(INIT_SLEEP_MS);
    WirePort2.begin(I2C_SDA2, I2C_SCL2, 100000);
    delay(500);
    for (int i = 0; i < MAX_RETRY; i++) {
        if (apds2.init() && apds2.enableLightSensor(false)) { sensor2_ok = true; break; }
        delay(500);
    }

    delay(INIT_SLEEP_MS);
    SPI.begin();
    rfid.PCD_Init();
    for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

    delay(INIT_SLEEP_MS);
    myServo.setPeriodHertz(50);
    myServo.attach(13, 500, 2400);
    myServo.write(0);

    delay(INIT_SLEEP_MS);
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) delay(500);
    Serial.println("WiFi Connected.");

    // 서버 접속은 setup 맨 마지막. 끊기면 loop에서 자동 재접속 + keep_alive + 장비 리스트 전송
    if (client.connect(serverIP, serverPort))
        Serial.println("Server Connected.");
    Serial.println("Init setup : End");
}

void loop() {
    if (!client.connected()) {
        client.stop();
        deviceListSent = false;
        if (client.connect(serverIP, serverPort)) {
            lastKeepAliveTime = millis();
            Serial.println("Reconnected to Server.");
        } else {
            delay(5000);
            return;
        }
    }

    if (client.connected() && !deviceListSent) {
        sendDeviceList();
        deviceListSent = true;
    }

    if (client.connected() && (millis() - lastKeepAliveTime >= PING_INTERVAL_MS)) {
        while (client.available() >= sizeof(UnifiedPacket))
            client.read((uint8_t*)&rxPkt, sizeof(UnifiedPacket));
        memset(&txPkt, 0, sizeof(txPkt));
        txPkt.type = TYPE_PING;
        if (client.write((uint8_t*)&txPkt, sizeof(UnifiedPacket)) != sizeof(UnifiedPacket)) {
            client.stop();
            return;
        }
        client.setTimeout(PONG_TIMEOUT_MS);
        size_t total = 0;
        unsigned long deadline = millis() + PONG_TIMEOUT_MS;
        while (total < sizeof(UnifiedPacket) && millis() < deadline) {
            if (client.available() > 0) {
                size_t n = client.read((uint8_t*)&rxPkt + total, sizeof(UnifiedPacket) - total);
                total += n;
            } else delay(10);
        }
        client.setTimeout(0);
        if (total != sizeof(UnifiedPacket) || rxPkt.type != TYPE_PONG) {
            Serial.println("Keep-alive timeout.");
            client.stop();
            return;
        }
        lastKeepAliveTime = millis();
    }

    // 게이트 열기/닫기 테스트: 서버에서 보낸 명령으로만 처리 (입구/출구/RFID 감지 시에는 이벤트만 전송)
    if (client.available() >= sizeof(UnifiedPacket)) {
        client.read((uint8_t*)&rxPkt, sizeof(UnifiedPacket));
        if (rxPkt.type == TYPE_CMD_OPEN) {
            openGate("SERVER");
        } else if (rxPkt.type == TYPE_CMD_CLOSE) {
            closeGate("SERVER");
        } else if (rxPkt.type == TYPE_CMD_WRITE) {
            memcpy(serverSiteID, &rxPkt.payload[1], 16);
            serverSiteID[15] = '\0';
            serverWriteSiteID = true;
            Serial.println("Ready to write SiteID to card...");
        }
    }

    if (millis() - lastDetectionTime > DETECTION_DELAY) {
        uint16_t l1 = 0, l2 = 0;
        if (sensor1_ok && apds1.readAmbientLight(l1) && l1 > 0 && l1 <= LIGHT_THRESHOLD) {
            char buf[16];
            snprintf(buf, sizeof(buf), "L:%d", l1);
            sendEvent(EV_ENTRY, "ENTRY", buf);
            Serial.printf("ENTRY_DETECTED (Light: %d)\n", l1);
            lastDetectionTime = millis();
        }
        delay(10);
        if (sensor2_ok) {
            l2 = readLightFromWire1();
            if (l2 > 0 && l2 <= LIGHT_THRESHOLD) {
                char buf[16];
                snprintf(buf, sizeof(buf), "L:%d", l2);
                sendEvent(EV_EXIT, "EXIT", buf);
                Serial.printf("EXIT_DETECTED (Light: %d)\n", l2);
                lastDetectionTime = millis();
            }
        }
    }

    if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
        char uidStr[16] = {0};
        char siteStr[16] = {0};
        for (byte i = 0; i < rfid.uid.size && i < 4; i++)
            snprintf(uidStr + i * 2, sizeof(uidStr) - i * 2, "%02x", rfid.uid.uidByte[i]);
        MFRC522::StatusCode status = rfid.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, RFID_BLOCK, &key, &(rfid.uid));
        if (status == MFRC522::STATUS_OK) {
            if (serverWriteSiteID) {
                byte buf[16];
                memset(buf, 0, 16);
                memcpy(buf, serverSiteID, 15);
                rfid.MIFARE_Write(RFID_BLOCK, buf, 16);
                Serial.println("SiteID written to card.");
                serverWriteSiteID = false;
                sendRFID(2, uidStr, serverSiteID);
            } else {
                byte buf[18];
                byte sz = 18;
                if (rfid.MIFARE_Read(RFID_BLOCK, buf, &sz) == MFRC522::STATUS_OK)
                    memcpy(siteStr, buf, 15);
                sendRFID(0, uidStr, siteStr);
            }
        }
        rfid.PICC_HaltA();
        rfid.PCD_StopCrypto1();
        delay(500);
    }
    delay(50);
}
