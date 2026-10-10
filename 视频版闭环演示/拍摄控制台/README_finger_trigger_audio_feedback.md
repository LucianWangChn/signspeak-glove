# 手指阈值触发音频 + OLED/振动控制

`finger_trigger_audio_feedback.py` 是拍摄专用脚本，不需要训练手语模型。

## 实现逻辑

从右手 BLE 接收传感器数据：

```text
R:Thumb:...,Index:...,Middle:...
```

然后执行：

| 条件 | 行为 |
|---|---|
| Thumb 从 ≤800 变成 >800 | 播放第一段音频 |
| Index 从 ≤800 变成 >800 | 播放第二段音频 |
| Middle 从 ≤800 变成 >800 | 播放第三段音频 |

只在“上升沿”触发一次，手指一直保持大于 800 不会重复播放。

新的触发会打断当前音频，立即播放新的音频。

## 音频映射

| 手指 | 音频 |
|---|---|
| 大拇指 Thumb | `audio_output\01_hospital_payment.wav` |
| 食指 Index | `audio_output\02_dont_worry.wav` |
| 中指 Middle | `audio_output\03_go_paperwork.wav` |

## OLED + 振动控制

运行脚本后，键盘输入：

```text
1
```

会通过 BLE 发送 `1`，触发手套：

```text
伤心水母 + conflict 振动 + 行吧
```

输入：

```text
2
```

会通过 BLE 发送 `2`，触发手套：

```text
开心水母 + positive_low 振动 + 行吧听你的
```

如果 BLE 写入不稳定，也可以接 USB 串口：

```powershell
python finger_trigger_audio_feedback.py --serial COM5 --no-ble-write
```

此时传感器仍走 BLE，键盘 1/2 通过串口发给 Arduino。

## 运行

```powershell
cd "<LOCAL_PROJECT_PATH>"
& <LOCAL_PROJECT_PATH>\AppData\Local\Programs\Python\Python310\python.exe finger_trigger_audio_feedback.py
```

## 参数

```text
--threshold 800       触发阈值
--debounce 0.8        同一手指防抖时间
--serial COM5         可选串口
--no-ble-write        键盘 1/2 不走 BLE，只走串口
```
