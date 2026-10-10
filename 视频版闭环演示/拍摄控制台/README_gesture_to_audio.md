# 手语识别触发电脑语音播放逻辑说明

这个目录里的 `gesture_to_audio_demo.py` 用来实现：

```text
手套做出对应手语动作
→ Python BLE 接收传感器数据
→ gesture_model_video.pkl 预测短句标签
→ 标签稳定后电脑自动播放对应音频
```

## 当前映射

| 标签 | 动作含义 | 播放音频 |
|---|---|---|
| 1 | 住院交费 | `01_hospital_payment.wav` |
| 2 | 不用担心陪你 | `02_dont_worry.wav` |
| 3 | 去办手续 | `03_go_paperwork.wav` |
| 0 | 静止 | 不播放 |

音频目录：

```text
..\拍摄控制台\audio_output\
```

## 还没训练好时怎么预览

先运行 mock 模式，不需要手套、不需要模型：

```powershell
cd "<LOCAL_PROJECT_PATH>"
& <LOCAL_PROJECT_PATH>\AppData\Local\Programs\Python\Python310\python.exe gesture_to_audio_demo.py --mock
```

然后输入：

```text
1
2
3
```

就会分别播放对应 WAV。

## 训练好后怎么运行

确认以下文件存在：

```text
<LOCAL_PROJECT_PATH>
<LOCAL_PROJECT_PATH>
```

然后运行：

```powershell
cd "<LOCAL_PROJECT_PATH>"
& <LOCAL_PROJECT_PATH>\AppData\Local\Programs\Python\Python310\python.exe gesture_to_audio_demo.py
```

## 防误触逻辑

脚本不是检测到一次就立刻播放，而是：

1. 模型置信度需要 ≥ 0.60。
2. 连续 3 次预测稳定为同一标签。
3. 同一个标签播放后 4 秒内不重复播放。

这样拍摄时更稳，不会因为窗口抖动疯狂重复播放。

## 需要注意

如果音频没生成，可以先运行：

```powershell
& <LOCAL_PROJECT_PATH>\AppData\Local\Programs\Python\Python310\python.exe generate_signspeak_voice_sapi.py
```
