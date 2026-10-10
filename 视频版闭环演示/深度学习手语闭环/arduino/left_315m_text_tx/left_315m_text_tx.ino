/*
  left_315m_text_tx.ino
  左手 315M 文本协议发射版：沿用最小版可工作的纯文本链路，发送完整五指 + MPU 数据。

  接线：
  - 315M TX DATA -> D13
  - 五指：Thumb=A0, Index=A1, Middle=A2, Ring=A3, Pinky=A6
  - MPU6050：SDA=A4, SCL=A5

  发射格式：
  L:Thumb:xxx,Index:xxx,Middle:xxx,Ring:xxx,Pinky:xxx,aX:xxx,aY:xxx,gZ:xxx
*/

#include <Wire.h>
#include <SPI.h>
#include <RH_ASK.h>

#define RF_TX_PIN 13
#define MPU_ADDR 0x68

const uint8_t fingerPins[5] = {A0, A1, A2, A3, A6};
const unsigned long SEND_INTERVAL_MS = 200;

RH_ASK rf(2000, 11, RF_TX_PIN, 10);
unsigned long lastSendMs = 0;
uint16_t seq = 0;

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

void setup() {
  Serial.begin(9600);
  Wire.begin();

  Serial.println(F("Left 315M text TX boot"));
  initMPU();

  if (rf.init()) {
    Serial.println(F("RF TX OK D13"));
  } else {
    Serial.println(F("RF TX FAIL"));
  }
}

void loop() {
  unsigned long now = millis();
  if (now - lastSendMs < SEND_INTERVAL_MS) return;
  lastSendMs = now;

  int thumb = analogRead(fingerPins[0]);
  int index = analogRead(fingerPins[1]);
  int middle = analogRead(fingerPins[2]);
  int ring = analogRead(fingerPins[3]);
  int pinky = analogRead(fingerPins[4]);

  int16_t ax = 0, ay = 0, gz = 0;
  readMPU(ax, ay, gz);

  char msg[96];
  snprintf(msg, sizeof(msg),
           "L:Thumb:%d,Index:%d,Middle:%d,Ring:%d,Pinky:%d,aX:%d,aY:%d,gZ:%d",
           thumb, index, middle, ring, pinky, ax, ay, gz);

  rf.send((uint8_t *)msg, strlen(msg));
  rf.waitPacketSent();

  Serial.print(F("SEND #"));
  Serial.print(seq++);
  Serial.print(F(" "));
  Serial.println(msg);
}
