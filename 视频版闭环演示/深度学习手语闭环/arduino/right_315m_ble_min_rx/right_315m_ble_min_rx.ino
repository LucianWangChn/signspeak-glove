/*
  right_315m_ble_min_rx.ino
  右手主控极简版：接收左手 315M + 采集右手五指/MPU + BLE 输出双手数据

  设计目标：尽量小，避免 Nano 内存溢出。
  本版本故意不包含 OLED / 中文点阵 / 水母 / 振动 / String。

  右手 Nano 接线：
  - BLE TX -> D2, BLE RX -> D3  (SoftwareSerial)
  - 315M RX DATA -> D4          (RadioHead RH_ASK RX)
  - 五指：Thumb=A0, Index=A1, Middle=A2, Ring=A3, Pinky=A6
  - MPU6050：SDA=A4, SCL=A5

  左手发送端需使用 left_315m_tx_full.ino，包结构必须一致。

  输出格式：
  R:Thumb:xxx,Index:xxx,Middle:xxx,Ring:xxx,Pinky:xxx,aX:xxx,aY:xxx,gZ:xxx
  L:Thumb:xxx,Index:xxx,Middle:xxx,Ring:xxx,Pinky:xxx,aX:xxx,aY:xxx,gZ:xxx
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

// RH_ASK(speed, rxPin, txPin, pttPin)
// 右手只接收，txPin/pttPin 给不用的脚位即可。
RH_ASK rf(2000, RF_RX_PIN, 13, 10);
SoftwareSerial BLESerial(BLE_RX_PIN, BLE_TX_PIN);

struct __attribute__((packed)) LeftPacket {
  uint8_t magic;      // 'L'
  uint8_t seq;
  uint16_t thumb;
  uint16_t index;
  uint16_t middle;
  uint16_t ring;
  uint16_t pinky;
  int16_t ax;
  int16_t ay;
  int16_t gz;
  uint8_t checksum;
};

struct SensorData {
  uint16_t thumb;
  uint16_t index;
  uint16_t middle;
  uint16_t ring;
  uint16_t pinky;
  int16_t ax;
  int16_t ay;
  int16_t gz;
};

SensorData rightData;
SensorData leftData;
unsigned long lastSendMs = 0;
unsigned long lastLeftMs = 0;
uint8_t lastLeftSeq = 0;

uint8_t calcChecksum(const uint8_t *data, uint8_t len) {
  uint8_t sum = 0;
  for (uint8_t i = 0; i < len; i++) sum ^= data[i];
  return sum;
}

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
  Wire.read(); Wire.read(); // az ignored
  Wire.read(); Wire.read(); // temp ignored
  Wire.read(); Wire.read(); // gx ignored
  Wire.read(); Wire.read(); // gy ignored
  int16_t gzRaw = (Wire.read() << 8) | Wire.read();

  ax = axRaw / 100;
  ay = ayRaw / 100;
  gz = gzRaw / 100;
  return true;
}

void readRightSensors() {
  rightData.thumb = analogRead(fingerPins[0]);
  rightData.index = analogRead(fingerPins[1]);
  rightData.middle = analogRead(fingerPins[2]);
  rightData.ring = analogRead(fingerPins[3]);
  rightData.pinky = analogRead(fingerPins[4]);

  if (!readMPU(rightData.ax, rightData.ay, rightData.gz)) {
    rightData.ax = 0;
    rightData.ay = 0;
    rightData.gz = 0;
  }
}

void pollLeft315M() {
  uint8_t buf[sizeof(LeftPacket)];
  uint8_t len = sizeof(buf);

  if (!rf.recv(buf, &len)) return;
  if (len != sizeof(LeftPacket)) return;

  LeftPacket pkt;
  memcpy(&pkt, buf, sizeof(pkt));

  if (pkt.magic != 'L') return;
  uint8_t ck = calcChecksum((uint8_t *)&pkt, sizeof(LeftPacket) - 1);
  if (ck != pkt.checksum) return;

  leftData.thumb = pkt.thumb;
  leftData.index = pkt.index;
  leftData.middle = pkt.middle;
  leftData.ring = pkt.ring;
  leftData.pinky = pkt.pinky;
  leftData.ax = pkt.ax;
  leftData.ay = pkt.ay;
  leftData.gz = pkt.gz;

  lastLeftSeq = pkt.seq;
  lastLeftMs = millis();
}

void printSensorLine(Stream &s, char hand, const SensorData &d) {
  s.print(hand);
  s.print(F(":Thumb:")); s.print(d.thumb);
  s.print(F(",Index:")); s.print(d.index);
  s.print(F(",Middle:")); s.print(d.middle);
  s.print(F(",Ring:")); s.print(d.ring);
  s.print(F(",Pinky:")); s.print(d.pinky);
  s.print(F(",aX:")); s.print(d.ax);
  s.print(F(",aY:")); s.print(d.ay);
  s.print(F(",gZ:")); s.println(d.gz);
}

void sendBothHands(Stream &s) {
  printSensorLine(s, 'R', rightData);

  // 没收到左手时也输出 L 行，但全 0，方便 Python 特征维度固定。
  if (millis() - lastLeftMs <= LEFT_TIMEOUT_MS) {
    printSensorLine(s, 'L', leftData);
  } else {
    SensorData zero = {0, 0, 0, 0, 0, 0, 0, 0};
    printSensorLine(s, 'L', zero);
  }
}

void setup() {
  Serial.begin(9600);
  BLESerial.begin(9600);
  Wire.begin();

  memset(&rightData, 0, sizeof(rightData));
  memset(&leftData, 0, sizeof(leftData));

  Serial.println(F("Right 315M BLE min RX boot"));
  initMPU();

  if (rf.init()) {
    Serial.println(F("RF RX OK D4"));
  } else {
    Serial.println(F("RF RX FAIL"));
  }

  Serial.println(F("No OLED in this min version"));
}

void loop() {
  pollLeft315M();

  unsigned long now = millis();
  if (now - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = now;
    readRightSensors();

    sendBothHands(BLESerial);
    sendBothHands(Serial);

    // 轻量调试：左手最近收到过才打印 seq，避免刷屏太多。
    if (now - lastLeftMs <= LEFT_TIMEOUT_MS) {
      Serial.print(F("LEFT_OK seq="));
      Serial.println(lastLeftSeq);
    }
  }
}
