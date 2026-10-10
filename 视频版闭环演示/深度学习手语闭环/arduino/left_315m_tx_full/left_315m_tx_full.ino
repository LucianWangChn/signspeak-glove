/*
  left_315m_tx_full.ino
  左手辅助节点：五指电位器 + MPU6050 -> 315M -> 右手/备用接收端

  Nano 接线：
  - 315M TX DATA -> D13
  - 五指：Thumb=A0, Index=A1, Middle=A2, Ring=A3, Pinky=A6
  - MPU6050：SDA=A4, SCL=A5
*/

#include <Wire.h>
#include <SPI.h>
#include <RH_ASK.h>

#define RF_TX_PIN 13
#define MPU_ADDR 0x68

const uint8_t fingerPins[5] = {A0, A1, A2, A3, A6};
const unsigned long SEND_INTERVAL_MS = 150;

// RH_ASK(speed, rxPin, txPin, pttPin)
RH_ASK rf(2000, 11, RF_TX_PIN, 10);

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

uint8_t seqNo = 0;
unsigned long lastSendMs = 0;

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
  Serial.println(err == 0 ? F("MPU6050 OK") : F("MPU6050 warning"));
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

LeftPacket makePacket() {
  LeftPacket pkt;
  pkt.magic = 'L';
  pkt.seq = seqNo++;
  pkt.thumb = analogRead(fingerPins[0]);
  pkt.index = analogRead(fingerPins[1]);
  pkt.middle = analogRead(fingerPins[2]);
  pkt.ring = analogRead(fingerPins[3]);
  pkt.pinky = analogRead(fingerPins[4]);

  if (!readMPU(pkt.ax, pkt.ay, pkt.gz)) {
    pkt.ax = 0;
    pkt.ay = 0;
    pkt.gz = 0;
  }

  pkt.checksum = calcChecksum((uint8_t *)&pkt, sizeof(LeftPacket) - 1);
  return pkt;
}

void setup() {
  Serial.begin(9600);
  Wire.begin();

  Serial.println(F("Left 315M TX full booting..."));
  initMPU();

  if (rf.init()) {
    Serial.println(F("RF TX OK on D13"));
  } else {
    Serial.println(F("RF TX init failed"));
  }
}

void loop() {
  unsigned long now = millis();
  if (now - lastSendMs < SEND_INTERVAL_MS) return;
  lastSendMs = now;

  LeftPacket pkt = makePacket();
  rf.send((uint8_t *)&pkt, sizeof(pkt));
  rf.waitPacketSent();

  Serial.print(F("L seq=")); Serial.print(pkt.seq);
  Serial.print(F(" Thumb=")); Serial.print(pkt.thumb);
  Serial.print(F(" Index=")); Serial.print(pkt.index);
  Serial.print(F(" Middle=")); Serial.println(pkt.middle);
}
