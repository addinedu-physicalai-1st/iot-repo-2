// ESP32 IR + RFID + 모터 통합 테스트 클라이언트
// 조도·RFID 이벤트 전송, 서버 명령으로 게이트 열기 / 카드 SiteID 쓰기

#include <Wire.h>
#include <SparkFun_APDS9960.h>
#include <ESP32Servo.h>
#include <SPI.h>
#include <MFRC522.h>
#include <WiFi.h>

#if 1
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


// 패킷 type: 1바이트
#define TYPE_PING        0xFE
#define TYPE_PONG        0xFD
#define TYPE_IR_EVENT    0
#define TYPE_RFID        1
#define TYPE_CMD_OPEN    2
#define TYPE_CMD_WRITE   3

#define EV_ENTRY   1
#define EV_EXIT    2
#define EV_RFID    3
#define EV_GATE_OPEN   4
#define EV_GATE_CLOSED 5

WiFiClient client;
unsigned long lastKeepAliveTime = 0;

#pragma pack(push, 1)
struct UnifiedPacket {
    uint8_t type;
    uint8_t payload[32];
};
#pragma pack(pop)

UnifiedPacket txPkt;
UnifiedPacket rxPkt;

SparkFun_APDS9960 apds1 = SparkFun_APDS9960();
SparkFun_APDS9960 apds2 = SparkFun_APDS9960();
Servo myServo;
MFRC522 rfid(5, 22);
MFRC522::MIFARE_Key key;
TwoWire WirePort2 = TwoWire(1);

const uint16_t LIGHT_THRESHOLD = 10;
const int RFID_BLOCK = 4;
bool isGateOpen = false;
bool serverWriteSiteID = false;
char serverSiteID[16] = {0};

void sendIREvent(uint8_t ev, const char* src, const char* ext) {
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

void openGate(const char* source) {
    if (!isGateOpen) {
        isGateOpen = true;
        sendIREvent(EV_GATE_OPEN, source, "");
        Serial.println("ACTION:GATE_OPEN_" + String(source));
        myServo.write(90);
        delay(3000);
        myServo.write(0);
        isGateOpen = false;
        sendIREvent(EV_GATE_CLOSED, "GATE", "");
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
    for (byte i = 0; i < 6; i++) key.keyByte[i] = 0xFF;

    myServo.setPeriodHertz(50);
    myServo.attach(13, 500, 2400);
    myServo.write(0);

    Wire.begin(32, 14);
    if (apds1.init()) { apds1.enableLightSensor(false); Serial.println("Sensor 1 Ready"); }
    WirePort2.begin(25, 26, 100000);
    if (apds2.init()) { apds2.enableLightSensor(false); Serial.println("Sensor 2 Ready"); }

    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) delay(500);
    Serial.println("--- IR+RFID+Motor Client ---");
}

unsigned long lastDetectionTime = 0;
const unsigned long DETECTION_DELAY = 2000; // 감지 후 1초간 재감지 방지

void loop() {
    if (!client.connected()) {
        client.stop();
        if (!client.connect(serverIP, serverPort)) {
            Serial.println("[Client] 서버 연결 실패. 5초 후 재시도...");
            delay(RECONNECT_INTERVAL_MS);
            return;
        }
        lastKeepAliveTime = millis();
        Serial.println("[Client] 접속되었습니다. " + String(serverIP));
        delay(300);
    }

    // Keep-alive
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
            Serial.println("[Client] Keep-alive 응답 없음.");
            client.stop();
            return;
        }
        lastKeepAliveTime = millis();
    }

    // 서버 명령 수신
    if (client.available() >= sizeof(UnifiedPacket)) {
        client.read((uint8_t*)&rxPkt, sizeof(UnifiedPacket));
        if (rxPkt.type == TYPE_CMD_OPEN) {
            Serial.println("[Client] 서버 명령: 게이트 열기");
            openGate("SERVER");
        } else if (rxPkt.type == TYPE_CMD_WRITE) {
            memcpy(serverSiteID, &rxPkt.payload[1], 16);
            serverSiteID[15] = '\0';
            serverWriteSiteID = true;
            Serial.println("[Client] 서버 명령: 카드에 SiteID 쓰기 대기");
        }
    }

    // 3. 조도 센서 감지 (쿨타임 적용)
    if (millis() - lastDetectionTime > DETECTION_DELAY) 
    {
        uint16_t light1 = 0, light2 = 0;

        // Sensor 1 (Entry)
        if (apds1.readAmbientLight(light1)) 
        {
            //Serial.printf("cool_Time_check1_ok\n");
            // 0이 들어오는 경우를 대비해 0보다 크고 임계값보다 낮은지 확인
            if (light1 > 0 && light1 <= LIGHT_THRESHOLD) 
            {
                char buf[16];
                snprintf(buf, sizeof(buf), "L:%d", light1);
                sendIREvent(EV_ENTRY, "ENTRY", buf);
                Serial.printf("ENTRY_DETECTED (Light: %d)\n", light1);
                lastDetectionTime = millis(); // 쿨타임 시작
            }
        }

        // Sensor 2 (Exit)
        light2 = readLightFromWire1();
        // 0이 들어오는 경우를 대비해 0보다 크고 임계값보다 낮은지 확인
        if (light2 > 0 && light2 <= LIGHT_THRESHOLD) 
        {
            char buf[16];
            snprintf(buf, sizeof(buf), "L:%d", light2);
            sendIREvent(EV_EXIT, "EXIT", buf);
            Serial.printf("EXIT_DETECTED (Light: %d)\n", light2);
            lastDetectionTime = millis(); // 쿨타임 시작
        }
    }

    /*          
    // 조도 센서
    uint16_t light1 = 0, light2 = 0;
    if (apds1.readAmbientLight(light1) && light1 > 0 && light1 <= LIGHT_THRESHOLD) {
        char buf[16];
        snprintf(buf, sizeof(buf), "L:%d", light1);
        sendIREvent(EV_ENTRY, "ENTRY", buf);
        Serial.printf("ENTRY_DETECTED (Light: %d)\n", light1);
    }
    light2 = readLightFromWire1();
    if (light2 > 0 && light2 <= LIGHT_THRESHOLD) {
        char buf[16];
        snprintf(buf, sizeof(buf), "L:%d", light2);
        sendIREvent(EV_EXIT, "EXIT", buf);
        Serial.printf("EXIT_DETECTED (Light: %d)\n", light2);
    }
    */
    
    // RFID
    if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) 
    {
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
                Serial.println("RFID 카드에 값을 저장하였습니다.");
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

    delay(150);
}
