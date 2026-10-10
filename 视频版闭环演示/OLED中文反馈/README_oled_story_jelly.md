# OLED 剧本中文 + 水母图案 Demo

## 文件

```text
oled_story_jelly_demo/oled_story_jelly_demo.ino
oled_story_jelly_demo/oled_story_words.h
```

## 特点

- 已调用 `display.setRotation(2)`，适配 OLED 屏幕物理装反。
- 支持 USB 串口输入命令切换。
- 支持 BLE 透传输入同样命令切换。
- 显示左侧水母图案 + 右侧中文短语。
- 中文为固定点阵，不依赖完整中文字库。

## 命令

| 命令 | 中文显示 | 水母状态 | 剧情用途 |
|---|---|---|---|
| TW | 妈妈担忧 | sad | 母亲说“行……吧……”后 |
| TS | 焦虑犹豫 | angry | 强负面/压力增强 |
| TA | 妈妈安心 | happy | 母亲说“行吧！听你的！”后 |
| TR | 放松接受 | happy | 安抚完成后 |
| TP | 住院交费 | happy | 第一句手语识别结果 |
| TB | 陪你一起 | happy | 第二句手语识别结果 |
| TG | 去办手续 | happy | 最后一句手语识别结果 |
| TC | 平静沟通 | happy | 默认状态 |

兼容命令：

- `NL` 会映射到 `TW`
- `NH` 会映射到 `TS`
- `PL` 会映射到 `TA`
- `NT` 会映射到 `TC`
- `T:TW` / `T:TA` 等也能识别

## 使用方法

1. 用 Arduino IDE 打开：

```text
<LOCAL_PROJECT_PATH>
```

2. 确保同目录存在：

```text
oled_story_words.h
```

3. 烧录后打开串口监视器，波特率 9600，输入：

```text
TW
TA
TP
TB
```

即可切换显示。

4. 如果 BLE 模块连接在 D2/D3，电脑端也可以通过 BLE 发送同样的命令。
