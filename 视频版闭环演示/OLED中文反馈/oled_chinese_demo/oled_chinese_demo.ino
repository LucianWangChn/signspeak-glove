/*
  oled_chinese_demo.ino
  OLED 固定中文点阵演示

  说明：
  1. 不依赖完整中文字库。
  2. Python/BLE 只发送状态码，如 TW/TA/TC/TS。
  3. Arduino 本地根据状态码 drawBitmap 显示固定中文词。

  需要先运行 make_oled_bitmaps.py 生成 oled_zh_words.h。
*/

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include "oled_zh_words.h"

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
#define OLED_RESET -1
#define OLED_ADDR 0x3C

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET);

String currentState = "TC";

void drawWord(const unsigned char *bmp, const char *en) {
  display.clearDisplay();
  display.drawBitmap(48, 12, bmp, 32, 16, SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(36, 38);
  display.print(en);
  display.display();
}

void showState(const String &cmd) {
  if (cmd == "TW") {
    drawWord(WORD_WORRY, "WORRY");
  } else if (cmd == "TS") {
    drawWord(WORD_ANXIETY, "ANXIETY");
  } else if (cmd == "TA") {
    drawWord(WORD_RELIEF, "RELIEF");
  } else if (cmd == "TR") {
    drawWord(WORD_RELAX, "RELAX");
  } else if (cmd == "TO") {
    drawWord(WORD_ACCEPT, "ACCEPT");
  } else {
    drawWord(WORD_CALM, "CALM");
  }
}

void setup() {
  Serial.begin(9600);
  Wire.begin();
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    Serial.println(F("OLED failed"));
    while (1) delay(100);
  }
  Serial.println(F("OLED Chinese bitmap demo ready"));
  showState(currentState);
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      currentState = cmd;
      showState(currentState);
      Serial.print(F("STATE="));
      Serial.println(currentState);
    }
  }
}
