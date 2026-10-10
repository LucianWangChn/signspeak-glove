/*
  right_315m_text_rx_ble.ino
  右手 315M 文本接收 + BLE 输出版。

  思路：最小纯文本 315M 已验证可用，所以这里不再用二进制结构体包，
  直接接收左手发来的 L:Thumb:... 文本行，再原样转发到 BLE/USB。

  为了小而稳：
  - 不带 OLED
  - 不带中文点阵
  - 不带水母
  - 不带振动
  - 不使用 String

  接线：
  - BLE TX -> D2, BLE RX -> D3
  - 315M RX DATA -> D4
  - 右手五指：A0/A1/A2/A3/A6
  - MPU6050：SDA=A4, SCL=A5
*/

#include <SoftwareSerial.h>
#include <Wire.h>
#include <SPI.h>
#include <RH_ASK.h>

#define BLE_RX_PIN 2
#define BLE_TX_PIN 3
#define RF_RX_PIN 4
#define MPU_ADDR 0x68

const uint8_t fingerPins[5] = {A0, A1, A2, A3, A6};
const unsigned long SEND_INTERVAL_MS = 200;
const unsigned long LEFT_TIMEOUT_MS = 1200;

SoftwareSerial BLESerial(BLE_RX_PIN, BLE_TX_PIN);
RH_ASK rf(2000, RF_RX_PIN, 13, 10);

char leftLine[RH_ASK_MAX_MESSAGE_LEN + 1];
bool hasLeft = false;
unsigned long lastLeftMs = 0;
unsigned long lastSendMs = 0;
uint32_t leftCount = 0;

void initMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0);
  byte err = Wire.endTransmission(true);
  Serial.println(err == 0 ? F("MPU OK") : F("MPU WARN"));
}

bool readMPU(int16_t &ax, int16_t &ay, int16_t &gz) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;

  uint8_t n = Wire.requestFrom(MPU_ADDR, 14, true);
  if (n < 14) return false;

  int16_t axRaw = (Wire.read() << 8) | Wire.read();
  int16_t ayRaw = (Wire.read() << 8) | Wire.read();
  Wire.read(); Wire.read();
  Wire.read(); Wire.read();
  Wire.read(); Wire.read();
  Wire.read(); Wire.read();
  int16_t gzRaw = (Wire.read() << 8) | Wire.read();

  ax = axRaw / 100;
  ay = ayRaw / 100;
  gz = gzRaw / 100;
  return true;
}

void pollLeft315M() {
  uint8_t buf[RH_ASK_MAX_MESSAGE_LEN];
  uint8_t len = sizeof(buf);

  if (!rf.recv(buf, &len)) return;
  if (len == 0) return;

  if (len >= sizeof(leftLine)) len = sizeof(leftLine) - 1;
  memcpy(leftLine, buf, len);
  leftLine[len] = '\0';

  if (leftLine[0] == 'L' && leftLine[1] == ':') {
    hasLeft = true;
    lastLeftMs = millis();
    leftCount++;
  }
}

void printRightLine(Stream &s) {
  int thumb = analogRead(fingerPins[0]);
  int index = analogRead(fingerPins[1]);
  int middle = analogRead(fingerPins[2]);
  int ring = analogRead(fingerPins[3]);
  int pinky = analogRead(fingerPins[4]);

  int16_t ax = 0, ay = 0, gz = 0;
  readMPU(ax, ay, gz);

  s.print(F("R:Thumb:")); s.print(thumb);
  s.print(F(",Index:")); s.print(index);
  s.print(F(",Middle:")); s.print(middle);
  s.print(F(",Ring:")); s.print(ring);
  s.print(F(",Pinky:")); s.print(pinky);
  s.print(F(",aX:")); s.print(ax);
  s.print(F(",aY:")); s.print(ay);
  s.print(F(",gZ:")); s.println(gz);
}

void printLeftOrZero(Stream &s) {
  if (hasLeft && (millis() - lastLeftMs <= LEFT_TIMEOUT_MS)) {
    s.println(leftLine);
  } else {
    s.println(F("L:Thumb:0,Index:0,Middle:0,Ring:0,Pinky:0,aX:0,aY:0,gZ:0"));
  }
}

void sendBoth(Stream &s) {
  printRightLine(s);
  printLeftOrZero(s);
}

void setup() {
  Serial.begin(9600);
  BLESerial.begin(9600);
  Wire.begin();

  Serial.println(F("Right 315M text RX BLE boot"));
  initMPU();

  if (rf.init()) {
    Serial.println(F("RF RX OK D4"));
  } else {
    Serial.println(F("RF RX FAIL"));
  }

  Serial.println(F("No OLED in this version"));
}

void loop() {
  pollLeft315M();

  unsigned long now = millis();
  if (now - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = now;

    sendBoth(BLESerial);
    sendBoth(Serial);

    if (hasLeft && now - lastLeftMs <= LEFT_TIMEOUT_MS) {
      Serial.print(F("LEFT_TEXT_OK count="));
      Serial.println(leftCount);
    }
  }
}
