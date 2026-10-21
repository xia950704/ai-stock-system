"""
ML模型模块：训练并生成交易信号
使用随机森林预测次日涨跌
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, confusion_matrix
import joblib
import os

MODEL_DIR = os.path.join(os.path.dirname(__file__), 'models')

def _model_path(symbol='default'):
    os.makedirs(MODEL_DIR, exist_ok=True)
    return os.path.join(MODEL_DIR, f'model_{symbol}.pkl')

class MLSignalGenerator:
    def __init__(self):
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=6,
            min_samples_split=20,
            random_state=42,
            class_weight='balanced'
        )
        self.feature_cols = None
        self.accuracy = 0.0

    def train(self, X, y):
        """时序交叉验证训练"""
        tscv = TimeSeriesSplit(n_splits=3)
        accs = []
        for train_idx, val_idx in tscv.split(X):
            X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
            self.model.fit(X_train, y_train)
            preds = self.model.predict(X_val)
            accs.append(accuracy_score(y_val, preds))

        # 用全量数据再训练一次（最终模型）
        self.model.fit(X, y)
        self.feature_cols = list(X.columns)
        self.accuracy = np.mean(accs)
        return self.accuracy

    def predict(self, X):
        """返回预测概率 [跌概率, 涨概率]"""
        proba = self.model.predict_proba(X)
        return proba[:, 1]  # 涨的概率

    def generate_signal(self, X, threshold=0.55):
        """
        生成交易信号
        1 = 买入 (预测涨概率 > threshold)
        0 = 持仓不动
        -1 = 卖出 (预测涨概率 < 1-threshold)
        """
        prob_up = self.predict(X)
        signals = np.where(prob_up > threshold, 1,
                          np.where(prob_up < (1 - threshold), -1, 0))
        return signals, prob_up

    def save(self, symbol='default'):
        path = _model_path(symbol)
        joblib.dump({'model': self.model, 'features': self.feature_cols, 'acc': self.accuracy}, path)

    def load(self, symbol='default'):
        path = _model_path(symbol)
        if os.path.exists(path):
            data = joblib.load(path)
            self.model = data['model']
            self.feature_cols = data['features']
            self.accuracy = data['acc']
            return True
        return False

    def feature_importance(self):
        """特征重要性"""
        if self.model and self.feature_cols:
            return sorted(zip(self.feature_cols, self.model.feature_importances_),
                         key=lambda x: x[1], reverse=True)
        return []

if __name__ == '__main__':
    from core.data import generate_synthetic_data, prepare_ml_data
    df = generate_synthetic_data()
    X, y, df_full = prepare_ml_data(df)
    ml = MLSignalGenerator()
    acc = ml.train(X, y)
    print(f"训练准确率: {acc:.2%}")
    print("特征重要性:")
    for feat, imp in ml.feature_importance():
        print(f"  {feat}: {imp:.3f}")