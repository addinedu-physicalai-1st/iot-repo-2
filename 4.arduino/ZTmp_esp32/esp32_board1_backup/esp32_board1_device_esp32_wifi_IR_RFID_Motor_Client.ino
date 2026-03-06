#include <Wire.h>
#include <SparkFun_APDS9960.h>
#include <ESP32Servo.h>
#include <SPI.h>
#include <MFRC522.h>
#include <WiFi.h>
#include <LiquidCrystal.h>

// [설정] 네트워크 환경
const char* ssid = "addinedu_201class_2-2.4G";
const char* password = "201class2!";
const char* serverIP = "192.168.0.137";
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
SparkFun_APDS9960 apds1 = SparkFun_APDS9960();
SparkFun_APDS9960 apds2 = SparkFun_APDS9960();
Servo myServo;

// RFID Setup: Moved to avoid LCD/I2C conflicts
// SS:5, RST:32, SCK:14, MISO:12, MOSI:15
MFRC522 rfid(5, 32);
MFRC522::MIFARE_Key key;

// LCD Setup: User requested RS(13), E(23), D4(19), D5(18), D6(17), D7(16)
LiquidCrystal lcd(13, 23, 19, 18, 17, 16);

// I2C Setup: User requested SDA(21), SCL(22)
#define I2C_SDA1 21
#define I2C_SCL1 22

// Second I2C remains on these pins (can be adjusted if needed)
#define I2C_SDA2 25
#define I2C_SCL2 26

// Servo Pin: Moved to Pin 27 to avoid LCD conflict
#define PIN_SERVO 27

const uint16_t PROXIMITY_THRESHOLD = 50; // Adjust based on physical distance
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

// 센서별 GUID(16자) + 영문 센서명(14자). 접속 시 서버 전송 → DB/리스트 연동
#define DEVICE_COUNT 4
static const struct { const char guid[17]; const char name[15]; } DEVICE_LIST[DEVICE_COUNT] = {
    { "ESP32-S1-ENTRY01", "EntryVehDetect" },  // 입구 차량 감지
    { "ESP32-S2-EXIT01 ", "ExitVehDetect" },   // 출구 차량 감지
    { "ESP32-RFID-01   ", "RFIDReader" },
    { "ESP32-GATE-01   ", "GateServo" },
};
bool deviceListSent = false;

// Helper: Update LCD Display
void updateDisplay(const char* line1, const char* line2 = "") {
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(line1);
    lcd.setCursor(0, 1);
    lcd.print(line2);
}

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

// 서버 명령(TYPE_CMD_OPEN) 수신 시에만 호출.
void openGate(const char* source) {
    if (!isGateOpen) {
        isGateOpen = true;
        sendEvent(EV_GATE_OPEN, source, "");
        Serial.println("ACTION: GATE_OPEN BY " + String(source));
        updateDisplay("GATE OPENING", source);
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
        updateDisplay("GATE CLOSING", source);
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

uint8_t readProximityFromWire1() {
    uint8_t val = 0;
    WirePort2.beginTransmission(0x39);
    WirePort2.write(0x9C); // Proximity data register
    if (WirePort2.endTransmission() != 0) return 0;
    WirePort2.requestFrom(0x39, 1);
    if (WirePort2.available() == 1) {
        val = WirePort2.read();
    }
    return val;
}

void setup() {
    Serial.begin(115200);
    
    // Initialize LCD
    lcd.begin(16, 2);
    updateDisplay("SYSTEM STARTING", "PLEASE WAIT...");
    
    Serial.println("Init setup : Start");
    delay(2000);

    Wire.begin(I2C_SDA1, I2C_SCL1);
    delay(500);
    for (int i = 0; i < MAX_RETRY; i++) {
        if (apds1.init() && apds1.enableProximitySensor(false)) { sensor1_ok = true; break; }
        delay(500);
    }

    WirePort2.begin(I2C_SDA2, I2C_SCL2, 100000);
    delay(500);
    for (int i = 0; i < MAX_RETRY; i++) {
        if (apds2.init() && apds2.enableProximitySensor(false)) { sensor2_ok = true; break; }
        delay(500);
    }

    // Initialize SPI with custom pins (SCK, MISO, MOSI)
    SPI.begin(14, 12, 15, 5); 
    rfid.PCD_Init();
    for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

    myServo.setPeriodHertz(50);
    myServo.attach(PIN_SERVO, 500, 2400);
    myServo.write(0);

    updateDisplay("CONNECTING WIFI", ssid);
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("WiFi Connected.");
    updateDisplay("WIFI CONNECTED", WiFi.localIP().toString().c_str());

    if (client.connect(serverIP, serverPort)) {
        Serial.println("Server Connected.");
        updateDisplay("SERVER CONNECTED", "PARKING SYSTEM");
    } else {
        updateDisplay("SERVER FAILED", "RETRYING...");
    }
    
    Serial.println("Init setup : End");
    delay(1000);
    updateDisplay("READY", "EXIT GATE");
}

void loop() {
    if (!client.connected()) {
        client.stop();
        deviceListSent = false;
        updateDisplay("RECONNECTING...", "SERVER");
        if (client.connect(serverIP, serverPort)) {
            lastKeepAliveTime = millis();
            Serial.println("Reconnected to Server.");
            updateDisplay("RECONNECTED", "EXIT GATE");
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
            updateDisplay("READY TO WRITE", "TAP CARD...");
        }
    }

    if (millis() - lastDetectionTime > DETECTION_DELAY) {
        uint8_t p1 = 0, p2 = 0;
        // Sensor 1 (Pins 21/22) -> EXIT as per user request
        if (sensor1_ok && apds1.readProximity(p1) && p1 >= PROXIMITY_THRESHOLD) {
            char buf[16];
            snprintf(buf, sizeof(buf), "P:%d", p1);
            sendEvent(EV_EXIT, "EXIT", buf);
            Serial.printf("EXIT_DETECTED (Prox: %d)\n", p1);
            updateDisplay("CAR EXITS NOW", "THANK YOU!");
            lastDetectionTime = millis();
        }
        delay(10);
        // Sensor 2 (Pins 25/26) -> ENTRY
        if (sensor2_ok) {
            p2 = readProximityFromWire1();
            if (p2 >= PROXIMITY_THRESHOLD) {
                char buf[16];
                snprintf(buf, sizeof(buf), "P:%d", p2);
                sendEvent(EV_ENTRY, "ENTRY", buf);
                Serial.printf("ENTRY_DETECTED (Prox: %d)\n", p2);
                updateDisplay("CAR DETECTED", "AT ENTRY");
                lastDetectionTime = millis();
            }
        }
    }

    if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {
        char uidStr[16] = {0};
        char siteStr[16] = {0};
        for (byte i = 0; i < rfid.uid.size && i < 4; i++)
            snprintf(uidStr + i * 2, sizeof(uidStr) - i * 2, "%02x", rfid.uid.uidByte[i]);
        
        updateDisplay("RFID READ", uidStr);
        
        MFRC522::StatusCode status = rfid.PCD_Authenticate(MFRC522::PICC_CMD_MF_AUTH_KEY_A, RFID_BLOCK, &key, &(rfid.uid));
        if (status == MFRC522::STATUS_OK) {
            if (serverWriteSiteID) {
                byte buf[16];
                memset(buf, 0, 16);
                memcpy(buf, serverSiteID, 15);
                rfid.MIFARE_Write(RFID_BLOCK, buf, 16);
                Serial.println("SiteID written to card.");
                updateDisplay("WRITE SUCCESS", serverSiteID);
                serverWriteSiteID = false;
                sendRFID(2, uidStr, serverSiteID);
            } else {
                byte buf[18];
                byte sz = 18;
                if (rfid.MIFARE_Read(RFID_BLOCK, buf, &sz) == MFRC522::STATUS_OK) {
                    memcpy(siteStr, buf, 15);
                    updateDisplay("ACCESS GRANTED", siteStr);
                }
                sendRFID(0, uidStr, siteStr);
            }
        } else {
            updateDisplay("AUTH FAILED", "TRY AGAIN");
        }
        rfid.PICC_HaltA();
        rfid.PCD_StopCrypto1();
        delay(1000);
        updateDisplay("READY", "EXIT GATE");
    }
    delay(50);
}


