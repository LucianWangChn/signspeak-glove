# -*- coding: utf-8 -*-
"""
train_deep_gesture_model_augmented.py

训练增强后的 dataset_deep_augmented_* 数据集。
默认自动选择 collector 目录下最新的 dataset_deep_augmented_*，输出 gesture_deep_model_augmented.pkl。
"""

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parent
FEATURE_COLS = [
    "R_Thumb", "R_Index", "R_Middle", "R_Ring", "R_Pinky", "R_aX", "R_aY", "R_gZ",
    "L_Thumb", "L_Index", "L_Middle", "L_Ring", "L_Pinky", "L_aX", "L_aY", "L_gZ",
]


def latest_augmented_dir():
    dirs = sorted(BASE_DIR.glob("dataset_deep_augmented_*"), key=lambda p: p.name)
    if not dirs:
        raise FileNotFoundError("没有找到 dataset_deep_augmented_* 目录")
    return dirs[-1]


def extract_features(csv_path: Path):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    label = str(df["label"].iloc[0])
    vals = df[FEATURE_COLS].astype(float)
    feats = []
    for col in FEATURE_COLS:
        x = vals[col].values
        feats.extend([
            float(np.mean(x)),
            float(np.std(x)),
            float(np.min(x)),
            float(np.max(x)),
            float(x[-1] - x[0]),
            float(np.mean(np.abs(np.diff(x)))) if len(x) > 1 else 0.0,
        ])
    return feats, label


def main():
    parser = argparse.ArgumentParser(description="训练增强版深度手语 MLP 模型")
    parser.add_argument("--data", default="", help="数据集目录，默认最新 dataset_deep_augmented_*")
    parser.add_argument("--out", default=str(BASE_DIR / "gesture_deep_model_augmented.pkl"))
    args = parser.parse_args()

    data_dir = Path(args.data) if args.data else latest_augmented_dir()
    files = sorted(data_dir.glob("*.csv"))
    if not files:
        raise FileNotFoundError(data_dir)

    X, y = [], []
    for path in files:
        feats, label = extract_features(path)
        X.append(feats)
        y.append(label)

    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y)
    print("data_dir:", data_dir)
    print("samples:", len(y), "features:", X.shape[1])
    print("labels:", {k: int(np.sum(y == k)) for k in sorted(set(y))})

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("mlp", MLPClassifier(hidden_layer_sizes=(256, 128, 64), max_iter=1200, random_state=42, early_stopping=True)),
    ])

    if len(set(y)) >= 2 and min(np.sum(y == k) for k in set(y)) >= 2:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.25, random_state=42, stratify=y
        )
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        print(classification_report(y_test, pred, zero_division=0))
        print("confusion_matrix:")
        print(confusion_matrix(y_test, pred, labels=sorted(set(y))))
    else:
        model.fit(X, y)
        print("样本太少，跳过验证。")

    # 最终用全量数据再拟合一次
    model.fit(X, y)
    payload = {
        "model": model,
        "feature_cols": FEATURE_COLS,
        "data_dir": str(data_dir),
        "labels": sorted(set(y)),
    }
    out = Path(args.out)
    with out.open("wb") as f:
        pickle.dump(payload, f)
    print("saved:", out)


if __name__ == "__main__":
    main()
