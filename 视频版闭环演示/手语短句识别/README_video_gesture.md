# 视频版手语短句识别说明

## 目标

本目录用于结课视频中的“手语转语音”展示，不做开放词表手语翻译，而是针对医院剧情中的固定短句做短句级分类。

## 标签设计

- 1 = 住院交费：妈，医生建议住院，我们现在去交费，可以吗？
- 2 = 不用担心陪你：妈，钱不用担心。我已经请好假了，可以陪您一起。
- 3 = 去办手续：走，办手续去。
- 0 = 静止：无动作/过渡/误触负样本

## 为什么这样做

当前硬件是五指电位器 + MPU6050，采集的是一段时间内的手部运动序列。现有训练脚本提取的是整段序列的统计特征，因此最适合识别“这一整段动作属于哪句话”，而不是逐词翻译国家通用手语。

## 推荐采集量

- 住院交费：30-50 条，每条 4 秒
- 不用担心陪你：30-50 条，每条 4 秒
- 去办手续：20-30 条，每条 3 秒
- 静止：20-30 条，每条 3 秒

如果时间紧，最低每句话 20 条，静止 15 条。

## 采集命令

```powershell
cd "<LOCAL_PROJECT_PATH>"
& <LOCAL_PROJECT_PATH>\AppData\Local\Programs\Python\Python310\python.exe ble_gesture_collector_video.py --duration 4
```

数据会保存到：

```text
<LOCAL_PROJECT_PATH>
```

## 训练命令

```powershell
cd "<LOCAL_PROJECT_PATH>"
& <LOCAL_PROJECT_PATH>\AppData\Local\Programs\Python\Python310\python.exe train_gesture_model_video.py
```

模型会保存为：

```text
gesture_model_video.pkl
```

## 实时预测命令

```powershell
cd "<LOCAL_PROJECT_PATH>"
& <LOCAL_PROJECT_PATH>\AppData\Local\Programs\Python\Python310\python.exe ble_gesture_predict_video.py
```

## 拍摄建议

正式拍摄时，只要稳定识别 1 和 2 两句话即可。第 3 句可以作为加分项，静止类用于减少误触。电脑播报可用预录音频或 TTS，预测界面作为 B-roll 展示。
