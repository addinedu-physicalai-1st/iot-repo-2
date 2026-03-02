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
const int INIT_SLEEP_MS = 3000; // WiFi 접속 후 3초 대기 (전원 안정화)
const int MAX_RETRY = 5;        // 센서 초기화 재시도 횟수

// 패킷 및 이벤트 타입 정의
#define TYPE_PING        0xFE
#define TYPE_PONG        0xFD
#define TYPE_IR_EVENT    0
#define TYPE_RFID        1
#define TYPE_CMD_OPEN    2
#define TYPE_CMD_WRITE   3

#define EV_ENTRY         1
#define EV_EXIT          2
#define EV_RFID          3
#define EV_GATE_OPEN     4
#define EV_GATE_CLOSED   5
#define EV_ERROR         99 // 센서 초기화 실패 에러

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
const unsigned long DETECTION_DELAY = 2000;
const unsigned long PING_INTERVAL_MS = 5000;   // 클라이언트가 5초마다 PING 전송
const unsigned long PONG_TIMEOUT_MS = 5000;     // PONG 대기 시간 

// 핀 설정 (문서 및 이전 논의 기반)
#define I2C_SDA1 32 // 
#define I2C_SCL1 14 // 

#define I2C_SDA2 25 // 
#define I2C_SCL2 26 // 


// 서버로 이벤트/에러 전송 함수
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

void openGate(const char* source) {
    if (!isGateOpen) {
        isGateOpen = true;
        sendEvent(EV_GATE_OPEN, source, "");
        Serial.println("ACTION: GATE_OPEN BY " + String(source));
        myServo.write(90);
        delay(3000);
        myServo.write(0);
        isGateOpen = false;
        sendEvent(EV_GATE_CLOSED, "GATE", "");
        Serial.println("ACTION: GATE_CLOSED");
    }
}

uint16_t readLightFromWire1() {
    uint16_t l = 0, h = 0;
    WirePort2.beginTransmission(0x39);
    WirePort2.write(0x94);
    if (WirePort2.endTransmission() != 0) 
    return 0;
    WirePort2.requestFrom(0x39, 2);
    if (WirePort2.available() == 2) 
    {
        l = WirePort2.read();
        h = WirePort2.read();
    }
    return (h << 8) | l;
}

void setup() 
{
    Serial.begin(115200);
    
    Serial.println("Init setup : Start section");

    // 3. n초 안정화 대기
    Serial.printf("Sensor1 Stabilizing for %dms...\n", INIT_SLEEP_MS);
    delay(INIT_SLEEP_MS);

    // 4. 센서 1 초기화 (Retry)
    Wire.begin(I2C_SDA1, I2C_SCL1); 

    for (int i = 0; i < MAX_RETRY; i++) 
    {
        Serial.printf("Sensor 1 Init Retry %d/%d\n", i+1, MAX_RETRY);

        if (apds1.init()) 
        {
            Serial.println(F("Sensor 1 APDS-9960 initialization complete"));
        } else 
        {
            Serial.println(F("Sensor 1 Something went wrong during APDS-9960 init!"));
        }

        // 조도 센서 활성화 (인터럽트 미사용)
        if (apds1.enableLightSensor(false)) 
        {
            Serial.println(F("Sensor 1 Light sensor is now running"));
            sensor1_ok = true;
        } 
        else 
        {
            Serial.println(F("Sensor 1 Something went wrong during light sensor init!"));
        }

        delay(500);
        
        if (sensor1_ok) 
        {
            Serial.println(F("---Sensor 1 APDS-9960 Light Sensor Test End OK---"));
            break;
        }
    }

#if 0
    if (sensor1_ok) 
    {   
        sendEvent(EV_ERROR, "SENSOR_1", "INIT_OK");
    }
    else(!sensor1_ok) 
    {   
        sendEvent(EV_ERROR, "SENSOR_1", "INIT_FAIL");
    }
#endif

    Serial.printf("Sensor2 Stabilizing for %dms...\n", INIT_SLEEP_MS);
    delay(INIT_SLEEP_MS);

    // 5. 센서 2 초기화 (Retry)
    WirePort2.begin(I2C_SDA2, I2C_SCL2, 100000); 
    //Wire.begin(I2C_SDA2, I2C_SCL2); // 통로를 센서 2핀으로 즉시 변경

    for (int i = 0; i < MAX_RETRY; i++) 
    {
        Serial.printf("Sensor 2 Init Retry %d/%d\n", i+1, MAX_RETRY);

        if (apds2.init()) 
        {
            Serial.println(F("Sensor 2 APDS-9960 initialization complete"));
        } else 
        {
            Serial.println(F("Sensor 2 Something went wrong during APDS-9960 init!"));
        }

        // 조도 센서 활성화 (인터럽트 미사용)
        if (apds2.enableLightSensor(false)) 
        {
            Serial.println(F("Sensor 2 Light sensor is now running"));
            sensor2_ok = true;
        } 
        else 
        {
            Serial.println(F("Sensor 2 Something went wrong during light sensor init!"));
        }

        delay(500);
        
        if (sensor2_ok) 
        {
            Serial.println(F("--- Sensor 2  APDS-9960 Light Sensor Test End OK---"));
            break;
        }
    }
    
    
#if 0
    if (sensor2_ok) 
    {   
        sendEvent(EV_ERROR, "SENSOR_2", "INIT_OK");
    }
    else(!sensor1_ok) 
    {   
        sendEvent(EV_ERROR, "SENSOR_2", "INIT_FAIL");
    }
#endif

    Serial.printf("RFID Init Stabilizing for %dms...\n", INIT_SLEEP_MS);
    delay(INIT_SLEEP_MS);

    // 6. RFID 설정
    SPI.begin();
    rfid.PCD_Init();
    for (byte i = 0; i < 6; i++) 
    {   
        key.keyByte[i] = 0xFF;
    }

    Serial.printf("Servo Motor Stabilizing for %dms...\n", INIT_SLEEP_MS);
    delay(INIT_SLEEP_MS);
    
    myServo.setPeriodHertz(50);
    myServo.attach(13, 500, 2400);
    myServo.write(0);

    Serial.printf("WiFi Stabilizing for %dms...\n", INIT_SLEEP_MS);
    delay(INIT_SLEEP_MS);

    // 7. WiFi 연결 마지막 실행
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) 
    {
        delay(500);
        Serial.print(".");
    }
    
    Serial.println("\nWiFi Connected.");

    // 2. 서버 사전 접속 (초기화 에러 보고를 위해)
    if (client.connect(serverIP, serverPort)) 
    {
        Serial.println("Server Connected.");
    }

    Serial.println("Init setup : End section");
}

void loop() {
    // 서버 연결 유지
    if (!client.connected()) {
        client.stop();
        if (client.connect(serverIP, serverPort)) {
            lastKeepAliveTime = millis();
            Serial.println("Reconnected to Server.");
        } else {
            delay(5000); return;
        }
    }

    // Keep-alive: 클라이언트가 5초마다 PING 전송 → 서버가 PONG 응답 (역할 고정)
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
            } else {
                delay(10);
            }
        }
        client.setTimeout(0);
        if (total != sizeof(UnifiedPacket) || rxPkt.type != TYPE_PONG) {
            Serial.println("Keep-alive timeout. Disconnecting.");
            client.stop();
            return;
        }
        lastKeepAliveTime = millis();
    }

    // 서버 명령 수신 (게이트 열기 / SiteID 쓰기 대기)
    if (client.available() >= sizeof(UnifiedPacket)) {
        client.read((uint8_t*)&rxPkt, sizeof(UnifiedPacket));
        if (rxPkt.type == TYPE_CMD_OPEN) {
            openGate("SERVER");
        } else if (rxPkt.type == TYPE_CMD_WRITE) {
            memcpy(serverSiteID, &rxPkt.payload[1], 16);
            serverSiteID[15] = '\0';
            serverWriteSiteID = true;
            Serial.println("Ready to write SiteID to card...");
        }
        // TYPE_PONG은 위 keep-alive 블록에서만 처리 (서버→클 PONG 수신)
    }

    // 조도 센서 감지 (정상 초기화된 경우만)
    if (millis() - lastDetectionTime > DETECTION_DELAY) 
    {
        uint16_t l1 = 0, l2 = 0;

        if (sensor1_ok)
        {
            if( apds1.readAmbientLight(l1) ) 
            {
                if (l1 > 0 && l1 <= LIGHT_THRESHOLD) 
                {
                    char buf[16];
                    snprintf(buf, sizeof(buf), "L:%d", l1);
                    sendEvent(EV_ENTRY, "ENTRY", buf);
                    Serial.printf("ENTRY_DETECTED (Light: %d)\n", l1);
                    lastDetectionTime = millis();
                }
            }
        }

        delay(10);

        if (sensor2_ok) 
        {
            l2 = readLightFromWire1();

            if (l2 > 0 && l2 <= LIGHT_THRESHOLD) 
            {
                char buf[16];
                snprintf(buf, sizeof(buf), "L:%d", l2);
                sendEvent(EV_EXIT, "EXIT", buf);
                Serial.printf("EXIT_DETECTED (Light: %d)\n", l2);
                lastDetectionTime = millis();
            }
        }
    }
    
    // RFID 로직
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