/*
  left_ble_slave.ino
  第二版汇总 - 左手 BLE 采集端

  硬件：
  - Arduino Nano + BLE 透传模块（JDY-23/HM-10/AT-09 等）
  - BLE 模块 TX -> Nano D2 (SoftwareSerial RX)
  - BLE 模块 RX -> Nano D3 (SoftwareSerial TX)
  - 五指电位器: A0/A1/A2/A3/A6
  - MPU6050: SDA=A4, SCL=A5
  - 315M 发射: D13 (可选，旧方案备用)

  BLE 模块配置（AT 指令预设）：
  - 角色：从机 (Peripheral)
  - 透传模式
  - 设备名：LEFT_GLOVE
  - UUID：0000ffe1-0000-1000-8000-00805f9b34fb

  功能：
  - 只采集左手传感器数据，通过 BLE 透传输出
  - 不接收情绪指令，不做 OLED/马达反馈
  - 电脑端直接连左手 BLE 读取数据

  输出格式（5Hz，减少 BLE 压力）：
  L:Thumb:xxx,Index:xxx,Middle:xxx,Ring:xxx,Pinky:xxx,aX:xxx,aY:xxx,gZ:xxx
*/

#include <SoftwareSerial.h>
#include <Wire.h>

#define BLE_RX_PIN 2
#define BLE_TX_PIN 3
#define MPU_ADDR 0x68

const int potPins[5] = {A0, A1, A2, A3, A6};
SoftwareSerial BLESerial(BLE_RX_PIN, BLE_TX_PIN);

unsigned long lastSendMs = 0;
const unsigned long SEND_INTERVAL_MS = 200;  // 5Hz

int thumbVal = 0, indexVal = 0, middleVal = 0, ringVal = 0, pinkyVal = 0;
int16_t ax = 0, ay = 0, az = 0, gx = 0, gy = 0, gz = 0;

void readSensors() {
  thumbVal = analogRead(potPins[0]); indexVal = analogRead(potPins[1]);
  middleVal = analogRead(potPins[2]); ringVal = analogRead(potPins[3]); pinkyVal = analogRead(potPins[4]);
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x3B);
  if (Wire.endTransmission(false) == 0) {
    Wire.requestFrom(MPU_ADDR, 14, true);
    if (Wire.available() >= 14) {
      ax=Wire.read()<<8|Wire.read(); ay=Wire.read()<<8|Wire.read(); az=Wire.read()<<8|Wire.read();
      Wire.read(); Wire.read();
      gx=Wire.read()<<8|Wire.read(); gy=Wire.read()<<8|Wire.read(); gz=Wire.read()<<8|Wire.read();
    }
  }
}

void sendSensorBLE() {
  BLESerial.print(F("L:Thumb:")); BLESerial.print(thumbVal);
  BLESerial.print(F(",Index:")); BLESerial.print(indexVal);
  BLESerial.print(F(",Middle:")); BLESerial.print(middleVal);
  BLESerial.print(F(",Ring:")); BLESerial.print(ringVal);
  BLESerial.print(F(",Pinky:")); BLESerial.print(pinkyVal);
  BLESerial.print(F(",aX:")); BLESerial.print(ax/100);
  BLESerial.print(F(",aY:")); BLESerial.print(ay/100);
  BLESerial.print(F(",gZ:")); BLESerial.println(gz/100);
}

void initMPU() {
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x6B); Wire.write(0);
  if (Wire.endTransmission(true) == 0) Serial.println(F("Left MPU6050 OK"));
  else Serial.println(F("Left MPU6050 FAILED"));
}

void setup() {
  Serial.begin(9600); BLESerial.begin(9600);
  Wire.begin();
  Serial.println(F("Left BLE slave booting..."));
  initMPU();
  BLESerial.println(F("LEFT_BLE_READY"));
  Serial.println(F("Left BLE ready. Sending sensor data at 5Hz."));
}

void loop() {
  unsigned long now = millis();
  if (now - lastSendMs >= SEND_INTERVAL_MS) {
    lastSendMs = now;
    readSensors();
    sendSensorBLE();
    // USB 调试
    Serial.print(F("L:Thumb:")); Serial.print(thumbVal);
    Serial.print(F(",Index:")); Serial.print(indexVal);
    Serial.print(F(",aX:")); Serial.print(ax/100);
    Serial.print(F(",gZ:")); Serial.println(gz/100);
  }
}
