# OLED 中文显示方案

## 结论

OLED 可以显示中文，但不建议直接用 Adafruit_SSD1306 `print("中文")`。默认 Adafruit_GFX 字库不含中文字形，直接打印 UTF-8 中文会乱码或显示异常。

## 可选方案

### 方案 A：U8g2 第三方中文字库

Arduino 常用 OLED 库 U8g2 支持部分中文字体，例如：

```cpp
u8g2_font_wqy12_t_gb2312
u8g2_font_wqy13_t_gb2312
u8g2_font_wqy14_t_gb2312
u8g2_font_unifont_t_chinese2
```

示例：

```cpp
#include <U8g2lib.h>

U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

void setup() {
  u8g2.begin();
  u8g2.enableUTF8Print();
  u8g2.setFont(u8g2_font_wqy12_t_gb2312);
}

void loop() {
  u8g2.clearBuffer();
  u8g2.setCursor(0, 18);
  u8g2.print("妈妈：担忧");
  u8g2.setCursor(0, 38);
  u8g2.print("情绪：焦虑");
  u8g2.sendBuffer();
}
```

风险：如果主控是 Arduino Nano / UNO，Flash 只有 32KB、SRAM 只有 2KB，完整中文字库可能导致程序过大或 OLED 初始化失败。此前项目已遇到过 OLED failed，说明内存余量要谨慎。

### 方案 B：固定汉字点阵，推荐用于视频

视频里只需要少量固定中文词：

```text
担忧 / 焦虑 / 安心 / 放松 / 平静 / 接受
```

推荐把这些词做成 16x16 点阵，存入 `PROGMEM`，Arduino 收到状态码后画对应点阵。

优势：

- 不需要完整中文字库
- 不需要 Arduino 解码 UTF-8 中文
- 占用空间小
- 对 Nano 更稳
- 适合结课视频拍摄

建议 BLE 协议：

```text
TW = 显示“担忧”
TA = 显示“安心”
TC = 显示“平静”
TS = 显示“焦虑”
```

Python 不直接发送中文，只发送状态码。中文由 Arduino 本地绘制。

## 推荐路线

如果只是为了视频和结课验收，优先做方案 B。若后续换 ESP32 / Arduino Mega 等资源更大的主控，再考虑 U8g2 中文字体。
