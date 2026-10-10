# Salary Cat OLED Animation

> 月薪喵 OLED 动画播放器 —— 在 Arduino Nano + SSD1306 128x64 屏幕上循环播放月薪喵跳舞动画。

## 项目简介

本项目将热门「月薪喵」跳舞 GIF 转换为 Arduino 可用的 SSD1306 位图数组，在 0.96 寸 OLED 屏幕上以约 12 FPS 流畅播放。

**核心特性：**
- 自动裁切 GIF 空白边缘，猫主体最大化显示
- 按高度填满 64px，居中显示，耳朵和脚完整保留
- 180° 屏幕翻转（`setRotation(2)`），适配手套佩戴方向
- 提高 SSD1306 刷新率到 ~370Hz，减少相机录像时的扫描横线
- 10 帧精简动画，Flash 占用约 76%（Arduino Nano 32KB 上限内）

## 硬件需求

| 组件 | 型号 | 说明 |
|---|---|---|
| 主控 | Arduino Nano (ATmega328P) | 32KB Flash, 2KB SRAM |
| OLED | SSD1306 128x64 I2C | 0.96 寸，地址 0x3C |
| 库 | Adafruit SSD1306 + Adafruit GFX | Arduino IDE 库管理器安装 |

## 接线

```
Arduino Nano    SSD1306 OLED
-----------     -----------
    5V    ---->    VCC
    GND   ---->    GND
    A4    ---->    SDA
    A5    ---->    SCL
```

## 使用方法

1. 用 Arduino IDE 打开 `salary_cat_oled_only.ino`
2. 安装库：`工具` → `管理库` → 搜索 `Adafruit SSD1306` 和 `Adafruit GFX` → 安装
3. 选择板子：`工具` → `板子` → `Arduino Nano`，处理器 `ATmega328P`
4. 编译并上传
5. OLED 开始循环播放月薪喵跳舞动画

## 帧数据来源

- 原始 GIF：`cat.GIF`（28 帧）
- 转换工具：`convert_gif_to_oled.py`（基于 [YueXinCat](https://github.com/EatFans/YueXinCat) 项目）
- 精简策略：每 3 帧取 1 帧，最终 10 帧，约 10KB Flash

## 项目背景

本项目是 [SIGNSPEAK / 智能情绪反馈手套](https://github.com/...) 工程的衍生作品。原工程是一个面向听障者与健听者的多模态情感转译外骨骼系统，手套通过 OLED 显示情绪反馈。月薪喵动画作为独立的趣味演示，展示了 OLED 在可穿戴设备上的动画能力。

## 许可证

MIT License — 详见 [LICENSE](LICENSE)

## 致谢

- [YueXinCat](https://github.com/EatFans/YueXinCat) — 月薪喵 OLED 播放器的原始灵感
- [SalaryCat](https://github.com/Einswen/SalaryCat) — 原始 GIF 素材
- [Adafruit](https://github.com/adafruit/Adafruit_SSD1306) — SSD1306 Arduino 库
