"""Exercise published sequence features and training with synthetic data only."""
from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

def main():
    path=Path(__file__).resolve().parents[1]/'手语识别/train_gesture_model.py'
    spec=importlib.util.spec_from_file_location('gesture_train',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rng=np.random.default_rng(42)
    features=[];labels=[]
    for label in range(2):
        for _ in range(12):
            values=rng.normal(label*5,0.05,size=(30,8))
            frame=pd.DataFrame(values,columns=module.FEATURE_ORDER)
            item=module.extract_sequence_features(frame)
            assert item.shape==(48,) and np.isfinite(item).all()
            features.append(item);labels.append(label)
    model=RandomForestClassifier(n_estimators=30,random_state=42)
    model.fit(np.array(features),labels)
    assert set(model.classes_)=={0,1}
    assert np.array_equal(model.predict(np.array(features)),labels)
    print('PASS: 48-dimensional sequence features, finite values and synthetic classification interface; no BLE, microphone or cloud access. Synthetic results are not real gesture accuracy.')

if __name__=='__main__':main()
