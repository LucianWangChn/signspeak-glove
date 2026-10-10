/*
  i2c_scanner.ino
  Scan I2C devices on Arduino Nano A4/A5.
  Use this when OLED begin failed but MPU6050 is OK.
*/

#include <Wire.h>

void setup() {
  Serial.begin(9600);
  Wire.begin();
  Serial.println("I2C scanner start");
}

void loop() {
  byte error, address;
  int count = 0;

  Serial.println("Scanning...");

  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();

    if (error == 0) {
      Serial.print("I2C device found at 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
      count++;
    } else if (error == 4) {
      Serial.print("Unknown error at 0x");
      if (address < 16) Serial.print("0");
      Serial.println(address, HEX);
    }
  }

  if (count == 0) Serial.println("No I2C devices found");
  else {
    Serial.print("Done. Device count: ");
    Serial.println(count);
  }

  delay(3000);
}
