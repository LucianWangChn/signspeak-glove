/*
  right_315m_plain_rx.ino
  315M 最小接收测试：只收 left_315m_plain_tx.ino 发来的纯文本 L:<seq>

  接线：315M RX DATA -> D4
  依赖库：RadioHead / RH_ASK

  说明：
  - 这版不包含 BLE、OLED、MPU、五指采集，专门排查 315M 是否能通。
  - 如果这版也收不到，问题基本在 315M 模块/接线/供电/频率/距离/天线。
*/

#include <RH_ASK.h>
#include <SPI.h>

#define RF_RX_PIN 4

// RH_ASK(speed, rxPin, txPin, pttPin)
RH_ASK rf(2000, RF_RX_PIN, 13, 10);

unsigned long lastBeat = 0;
uint32_t recvCount = 0;

void setup() {
  Serial.begin(9600);
  Serial.println(F("Right 315M plain RX boot"));

  if (rf.init()) {
    Serial.println(F("RF RX OK D4"));
  } else {
    Serial.println(F("RF RX FAIL"));
  }

  Serial.println(F("Waiting for L:<seq> ..."));
}

void loop() {
  uint8_t buf[RH_ASK_MAX_MESSAGE_LEN];
  uint8_t len = sizeof(buf);

  if (rf.recv(buf, &len)) {
    recvCount++;
    Serial.print(F("RX #"));
    Serial.print(recvCount);
    Serial.print(F(" len="));
    Serial.print(len);
    Serial.print(F(" data="));

    for (uint8_t i = 0; i < len; i++) {
      char c = (char)buf[i];
      if (c >= 32 && c <= 126) Serial.print(c);
      else Serial.print('.');
    }
    Serial.println();
  }

  // 心跳：说明程序没死，只是没收到包
  if (millis() - lastBeat > 2000) {
    lastBeat = millis();
    Serial.print(F("WAIT count="));
    Serial.println(recvCount);
  }
}
