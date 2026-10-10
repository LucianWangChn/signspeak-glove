# 深度学习手语闭环

已生成：左右手 ino、新 control、新采集/训练脚本。

## 烧录
- 左手：`arduino/left_315m_tx_full/left_315m_tx_full.ino`
- 右手：`arduino/right_ble_315m_master_full/right_ble_315m_master_full.ino`
- 右手 ino 需要同目录放 `oled_mother_lines.h`。

## 采集
串口助手 TCP Server 127.0.0.1:9001 打开后：

```powershell
cd "<LOCAL_PROJECT_PATH>"
python collect_deep_gesture_tcp.py --duration 4
```

## 训练更大的模型

```powershell
python train_deep_gesture_model.py
```

当前用 MLP `(256,128,64)`，比原随机森林更大；如果后面数据量足够，可再换 PyTorch LSTM/CNN。

## 运行 control

```powershell
cd "<LOCAL_PROJECT_PATH>"
python sign_predict_audio_control.py
```

延时：标签 1/2 为 15 秒，标签 3 为 8 秒。键盘 1/2 仍可控 OLED。
