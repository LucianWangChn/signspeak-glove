"""
train_gesture_model.py
第二版手语识别训练脚本

从 serial_gesture_collector.py 采集的 CSV 中训练一个轻量级随机森林模型。
这个版本适合结课快速跑通：每次动作采集一段序列，脚本对每段序列提取统计特征。

用法：
python train_gesture_model.py --data dataset --output gesture_model.pkl
"""

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURE_ORDER = ["Thumb", "Index", "Middle", "Ring", "Pinky", "aX", "aY", "gZ"]


def extract_sequence_features(df: pd.DataFrame) -> np.ndarray:
    values = df[FEATURE_ORDER].astype(float).values
    feats = []
    # 每个通道的统计特征
    feats.extend(values.mean(axis=0))
    feats.extend(values.std(axis=0))
    feats.extend(values.min(axis=0))
    feats.extend(values.max(axis=0))
    feats.extend(values[-1] - values[0])
    # 动作强度：一阶差分平均绝对值
    if len(values) > 1:
        diffs = np.diff(values, axis=0)
        feats.extend(np.mean(np.abs(diffs), axis=0))
    else:
        feats.extend(np.zeros(values.shape[1]))
    return np.array(feats, dtype=np.float32)


def load_dataset(data_dir: Path):
    X, y = [], []
    files = sorted(data_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"没有找到 CSV 数据：{data_dir}")

    for path in files:
        df = pd.read_csv(path, encoding="utf-8-sig")
        if not all(col in df.columns for col in FEATURE_ORDER):
            print(f"跳过字段不完整文件：{path}")
            continue
        if "label" in df.columns:
            label = str(df["label"].iloc[0])
        else:
            # 文件名格式：1_你好_20260529_213000.csv
            parts = path.stem.split("_")
            label = parts[1] if len(parts) >= 2 else parts[0]
        X.append(extract_sequence_features(df))
        y.append(label)

    if not X:
        raise ValueError("没有可用训练样本。")
    return np.vstack(X), np.array(y)


def main():
    parser = argparse.ArgumentParser(description="训练第二版手语识别模型")
    parser.add_argument("--data", default=str(Path(__file__).parent / "dataset"), help="CSV 数据目录")
    parser.add_argument("--output", default=str(Path(__file__).parent / "gesture_model.pkl"), help="模型输出路径")
    parser.add_argument("--test-size", type=float, default=0.25)
    args = parser.parse_args()

    X, y = load_dataset(Path(args.data))
    labels, counts = np.unique(y, return_counts=True)
    print("样本统计：")
    for label, count in zip(labels, counts):
        print(f"  {label}: {count}")

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", RandomForestClassifier(
            n_estimators=200,
            max_depth=None,
            random_state=42,
            class_weight="balanced",
        )),
    ])

    # 样本太少时不划分验证集，先保证能训练出可用模型。
    min_count = counts.min()
    if len(y) >= 8 and len(labels) >= 2 and min_count >= 2:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=args.test_size, random_state=42, stratify=y
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)
        print("\n验证结果：")
        print(classification_report(y_test, y_pred, zero_division=0))
        print("混淆矩阵：")
        print(confusion_matrix(y_test, y_pred, labels=labels))
    else:
        print("样本数量较少，跳过验证集划分，使用全部数据训练。")
        model.fit(X, y)

    out = Path(args.output)
    with out.open("wb") as f:
        pickle.dump({
            "model": model,
            "feature_order": FEATURE_ORDER,
            "labels": sorted(labels.tolist()),
        }, f)
    print(f"模型已保存：{out.resolve()}")


if __name__ == "__main__":
    main()
