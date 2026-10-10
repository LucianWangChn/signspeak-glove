#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
#define OLED_RESET    -1
#define ADDR_3C 0x3C
#define ADDR_3D 0x3D

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

void setup() {
  Wire.begin();
  bool ok = false;
  
  // 先试 0x3C
  if (display.begin(SSD1306_SWITCHCAPVCC, ADDR_3C)) {
    ok = true;
  }
  // 不行再试 0x3D
  else if (display.begin(SSD1306_SWITCHCAPVCC, ADDR_3D)) {
    ok = true;
  }
  
  if (!ok) {
    // 两个地址都不行 → 快闪 LED
    pinMode(13, OUTPUT);
    while (1) {
      digitalWrite(13, !digitalRead(13));
      delay(200);
    }
  }
  
  // 成功 → 显示测试图案
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(2);
  display.setCursor(10, 20);
  display.println(F("HELLO"));
  display.setTextSize(1);
  display.setCursor(10, 50);
  display.println(F("If you see this,"));
  display.println(F("OLED works!"));
  display.display();
}

void loop() {
  // 什么都不做，停在这里
}
