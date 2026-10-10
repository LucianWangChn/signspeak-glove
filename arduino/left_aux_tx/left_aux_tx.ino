/*
  left_aux_tx.ino
  第二版汇总 - 左手辅助发送程序

  Hardware role:
  - Left hand is an auxiliary node.
  - It reads left-hand finger sensors and MPU6050.
  - It sends compact sensor packets to the right master through 315M using RadioHead.
  - It does not control the main demo flow. If the 315M link is unstable, the right hand still works.

  Wiring:
  - 315M TX DATA / ATAD -> Nano D13
  - Fingers: Thumb=A0, Index=A1, Middle=A2, Ring=A3, Pinky=A6
  - MPU6050 I2C: SDA=A4, SCL=A5

  Required libraries:
  - Wire
  - SPI
  - RadioHead: RH_ASK
*/

#include <Wire.h>
#include <SPI.h>
#include <RH_ASK.h>

#define RF_TX_PIN 13
#define MPU_ADDR 0x68

const uint8_t fingerPins[5] = {A0, A1, A2, A3, A6};
const unsigned long SEND_INTERVAL_MS = 200;  // 5Hz, lower rate improves 315M stability

// RH_ASK(speed, rxPin, txPin, pttPin). rxPin/pttPin are unused placeholders here.
RH_ASK rfDriver(2000, 11, RF_TX_PIN, 10);

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

bool readMPU(int16_t &ax, int16_t &ay, int16_t &gz) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;

  uint8_t n = Wire.requestFrom(MPU_ADDR, 14, true);
  if (n < 14) return false;

  ax = Wire.read() << 8 | Wire.read();
  ay = Wire.read() << 8 | Wire.read();
  Wire.read(); Wire.read(); // az ignored for compact packet
  Wire.read(); Wire.read(); // temperature ignored
  Wire.read(); Wire.read(); // gx ignored
  Wire.read(); Wire.read(); // gy ignored
  gz = Wire.read() << 8 | Wire.read();
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
  pkt.ax = 0;
  pkt.ay = 0;
  pkt.gz = 0;

  int16_t axRaw = 0, ayRaw = 0, gzRaw = 0;
  if (readMPU(axRaw, ayRaw, gzRaw)) {
    // Scale down to keep values compact and consistent with old sign-language format.
    pkt.ax = axRaw / 100;
    pkt.ay = ayRaw / 100;
    pkt.gz = gzRaw / 100;
  }

  pkt.checksum = calcChecksum((uint8_t *)&pkt, sizeof(LeftPacket) - 1);
  return pkt;
}

void initMPU() {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(0x6B);
  Wire.write(0);
  byte err = Wire.endTransmission(true);
  if (err == 0) {
    Serial.println("MPU6050 OK");
  } else {
    Serial.println("MPU6050 warning: check I2C wiring");
  }
}

void setup() {
  Serial.begin(9600);
  Wire.begin();

  Serial.println("Left auxiliary transmitter booting...");

  initMPU();

  if (!rfDriver.init()) {
    Serial.println("RadioHead TX init failed");
  } else {
    Serial.println("RadioHead TX ready on D13");
  }
}

void loop() {
  unsigned long now = millis();
  if (now - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = now;

    LeftPacket pkt = makePacket();
    rfDriver.send((uint8_t *)&pkt, sizeof(pkt));
    rfDriver.waitPacketSent();

    Serial.print("Sent L seq="); Serial.print(pkt.seq);
    Serial.print(" Thumb="); Serial.print(pkt.thumb);
    Serial.print(" Index="); Serial.println(pkt.index);
  }
}
