/*
  left_315m_plain_tx.ino
  315M 最小发射测试：只发纯文本 L:<seq>

  接线：315M TX DATA -> D13
  依赖库：RadioHead / RH_ASK
*/

#include <RH_ASK.h>
#include <SPI.h>

#define RF_TX_PIN 13

// RH_ASK(speed, rxPin, txPin, pttPin)
RH_ASK rf(2000, 11, RF_TX_PIN, 10);

uint16_t seq = 0;

void setup() {
  Serial.begin(9600);
  Serial.println(F("Left 315M plain TX boot"));

  if (rf.init()) {
    Serial.println(F("RF TX OK D13"));
  } else {
    Serial.println(F("RF TX FAIL"));
  }
}

void loop() {
  char msg[16];
  snprintf(msg, sizeof(msg), "L:%u", seq++);

  rf.send((uint8_t *)msg, strlen(msg));
  rf.waitPacketSent();

  Serial.print(F("SEND "));
  Serial.println(msg);
  delay(500);
}
