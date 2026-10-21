#!/usr/bin/env python3
"""
预测引擎

基于历史数据进行价格预测：
1. 加载历史价格数据
2. 运行多模型预测（ARIMA、Prophet、LSTM）
3. 输出预测区间和置信度
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

# 尝试导入预测库
try:
    import numpy as np
    import pandas as pd
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("⚠️ numpy/pandas 未安装，使用简化预测")


class PredictionEngine:
    """预测引擎"""
    
    def __init__(self):
        self.historical_data = {}
        self.models = {}
        self.default_data_path = Path.home() / "obsidian" / "all about xia" / "01-股票投研" / "data"
        
        # 路径预检
        self._validate_paths()
    
    def _validate_paths(self):
        """路径预检"""
        # 确保默认数据目录存在（不报错，只提示）
        if not self.default_data_path.exists():
            print(f"⚠️ 默认数据目录不存在: {self.default_data_path}")
            print("   请确保股票数据存放在该目录，或使用 data_path 参数指定路径")
    
    def load_data(self, stock_code: str, data_path: Optional[str] = None, use_latest_price: bool = False) -> bool:
        """
        加载历史价格数据
        
        Args:
            stock_code: 股票代码
            data_path: 数据路径
        
        Returns:
            是否成功
        """
        if data_path:
            path = Path(data_path)
        else:
            # 默认从 vault data/stocks/ 加载
            path = Path.home() / "obsidian" / "all about xia" / "01-股票投研" / "data" / f"{stock_code}.csv"
        
        # 如果 CSV 不存在，尝试从最新价格 JSON 加载（数据降级方案）
        if use_latest_price and not path.exists():
            price_json_path = Path.home() / "obsidian" / "all about xia" / "01-股票投研" / "data" / f"price_data_latest.json"
            if price_json_path.exists():
                try:
                    import json
                    with open(price_json_path, 'r', encoding='utf-8') as f:
                        price_data = json.load(f)
                    price_info = price_data.get('price_data', {}).get(stock_code)
                    if price_info and price_info.get('success'):
                        # 用当前价格 + 假设历史数据生成简化预测
                        current_price = price_info.get('price')
                        change_pct = price_info.get('change_pct', 0)
                        self.historical_data[stock_code] = {
                            "dates": [datetime.now().strftime('%Y-%m-%d')],
                            "prices": [current_price],
                            "change_pct": change_pct,
                            "use_latest_only": True
                        }
                        print(f"✅ 已加载 {stock_code}: 最新价 ¥{current_price} (仅最新价格)")
                        return True
                except Exception as e:
                    print(f"⚠️ 从 price_data JSON 加载失败: {e}")
        
        if not path.exists():
            print(f"⚠️ 数据文件不存在: {path}")
            return False
        
        try:
            if HAS_NUMPY:
                import pandas as pd
                df = pd.read_csv(path)
                
                # 自动检测列名
                date_col = next((c for c in df.columns if 'date' in c.lower() or 'time' in c.lower()), df.columns[0])
                price_col = next((c for c in df.columns if 'close' in c.lower() or 'price' in c.lower()), df.columns[1])
                volume_col = next((c for c in df.columns if 'volume' in c.lower() or 'vol' in c.lower()), None)
                
                self.historical_data[stock_code] = {
                    "dates": df[date_col].tolist(),
                    "prices": df[price_col].tolist(),
                    "volumes": df[volume_col].tolist() if volume_col else []
                }
            else:
                # 简化加载 - 尝试多种格式
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # 检测表头
                if not lines:
                    print(f"⚠️ 文件为空: {path}")
                    return False
                header = lines[0].strip().split(',')
                is_header = any(kw in ' '.join(header).lower() for kw in ['date', 'time', 'close', 'price', 'open', 'high', 'low'])
                
                data_lines = lines[1:] if is_header else lines
                prices = []
                dates = []
                
                for line in data_lines[-100:]:  # 取最近 100 条
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        try:
                            # 尝试检测日期列和价格列
                            for i, p in enumerate(parts):
                                try:
                                    float(p)
                                    # 找到第一个数字列作为价格
                                    prices.append(float(p))
                                    if i > 0:
                                        dates.append(parts[0])
                                    break
                                except Exception:
                                    continue
                        except Exception:
                            pass
                
                self.historical_data[stock_code] = {
                    "dates": dates,
                    "prices": prices
                }
            
            print(f"✅ 已加载 {stock_code}: {len(self.historical_data[stock_code].get('prices', []))} 条数据")
            return True
        except Exception as e:
            print(f"❌ 加载失败: {e}")
            return False
    
    def predict_arima(self, stock_code: str, horizon: int = 5) -> Dict:
        """
        ARIMA 预测（简化版）
        
        Args:
            stock_code: 股票代码
            horizon: 预测天数
        
        Returns:
            预测结果
        """
        if stock_code not in self.historical_data:
            return {"error": "数据未加载"}
        
        prices = self.historical_data[stock_code].get("prices", [])
        if len(prices) < 10:
            return {"error": "数据不足"}
        
        if HAS_NUMPY:
            # 使用简单移动平均 + 波动率
            prices_array = np.array(prices[-30:])
            ma = np.mean(prices_array)
            std = np.std(prices_array)
            
            # 预测未来价格（带随机游走）
            predictions = []
            current = prices[-1]
            for i in range(horizon):
                # 带漂移的随机游走
                drift = (prices[-1] - prices[-5]) / 5 if len(prices) >= 5 else 0
                current = current + drift + np.random.normal(0, std * 0.3)
                predictions.append(round(current, 2))
            
            return {
                "model": "ARIMA (简化)",
                "current_price": prices[-1],
                "predictions": predictions,
                "confidence_interval": {
                    "upper": round(predictions[-1] + 1.96 * std, 2),
                    "lower": round(predictions[-1] - 1.96 * std, 2)
                },
                "trend": "up" if predictions[-1] > prices[-1] else "down"
            }
        else:
            # 极简版：线性外推
            last_5 = prices[-5:]
            avg_change = sum(last_5[i] - last_5[i-1] for i in range(1, 5)) / 4
            predictions = [round(prices[-1] + avg_change * (i+1), 2) for i in range(horizon)]
            
            return {
                "model": "线性外推",
                "current_price": prices[-1],
                "predictions": predictions,
                "trend": "up" if avg_change > 0 else "down"
            }
    
    def predict_prophet_style(self, stock_code: str, horizon: int = 5) -> Dict:
        """
        Prophet 风格预测（简化版）
        
        模拟 Prophet 的分解：趋势 + 季节性
        
        Args:
            stock_code: 股票代码
            horizon: 预测天数
        
        Returns:
            预测结果
        """
        if stock_code not in self.historical_data:
            return {"error": "数据未加载"}
        
        prices = self.historical_data[stock_code].get("prices", [])
        if len(prices) < 20:
            return {"error": "数据不足"}
        
        if HAS_NUMPY:
            prices_array = np.array(prices[-60:])
            
            # 趋势：线性回归
            x = np.arange(len(prices_array))
            slope = np.polyfit(x, prices_array, 1)[0]
            
            # 季节性：7 天周期
            seasonal = np.zeros(7)
            for i in range(7):
                seasonal[i] = np.mean(prices_array[i::7]) - np.mean(prices_array)
            
            # 预测
            predictions = []
            last_date_idx = len(prices) % 7
            for i in range(horizon):
                trend = slope * (len(prices_array) + i)
                season = seasonal[(last_date_idx + i) % 7]
                pred = np.mean(prices_array) + trend + season
                predictions.append(round(pred, 2))
            
            return {
                "model": "Prophet (简化)",
                "current_price": prices[-1],
                "predictions": predictions,
                "trend_component": round(slope * horizon, 2),
                "seasonal_component": round(seasonal[last_date_idx % 7], 2)
            }
        else:
            return self.predict_arima(stock_code, horizon)
    
    def predict_ensemble(self, stock_code: str, horizon: int = 5) -> Dict:
        """
        集成预测（多模型加权平均）
        
        Args:
            stock_code: 股票代码
            horizon: 预测天数
        
        Returns:
            预测结果
        """
        # 运行多个模型
        arima_result = self.predict_arima(stock_code, horizon)
        prophet_result = self.predict_prophet_style(stock_code, horizon)
        
        if "error" in arima_result or "error" in prophet_result:
            return arima_result if "error" in arima_result else prophet_result
        
        # 加权平均
        weights = {"arima": 0.5, "prophet": 0.5}
        
        ensemble_predictions = []
        for i in range(horizon):
            pred = (
                arima_result["predictions"][i] * weights["arima"] +
                prophet_result["predictions"][i] * weights["prophet"]
            )
            ensemble_predictions.append(round(pred, 2))
        
        # 计算模型分歧度
        disagreement = []
        for i in range(horizon):
            disagreement.append(abs(
                arima_result["predictions"][i] - prophet_result["predictions"][i]
            ))
        
        avg_disagreement = sum(disagreement) / len(disagreement)
        
        return {
            "model": "Ensemble",
            "current_price": arima_result["current_price"],
            "predictions": ensemble_predictions,
            "model_disagreement": round(avg_disagreement, 2),
            "confidence": "high" if avg_disagreement < 2 else "medium" if avg_disagreement < 5 else "low",
            "components": {
                "arima": arima_result,
                "prophet": prophet_result
            }
        }
    
    def get_prediction_report(self, stock_code: str, horizon: int = 5) -> Dict:
        """
        生成综合预测报告
        
        Args:
            stock_code: 股票代码
            horizon: 预测天数
        
        Returns:
            预测报告
        """
        # 检查是否仅使用最新价格
        stock_data = self.historical_data.get(stock_code, {})
        if stock_data.get("use_latest_only"):
            # 简化模式：仅最新价格，返回基于当前价格的估算
            current_price = stock_data.get("prices", [0])[0]
            change_pct = stock_data.get("change_pct", 0)
            
            # 估算波动率（基于涨跌幅）
            estimated_vol = abs(change_pct) / 100 * 20  # 简化估算
            
            return {
                "stock_code": stock_code,
                "current_price": current_price,
                "change_pct": change_pct,
                "horizon": horizon,
                "prediction": {
                    "predictions": [round(current_price * (1 + change_pct/100), 2)] * horizon,
                    "method": "简化估算（仅最新价格）",
                    "confidence": "低",
                    "note": "缺少历史数据，使用当前价格外推"
                },
                "recommendation": f"当前价 ¥{current_price}，涨跌幅 {change_pct}%。建议等待更多历史数据后再做预测。",
                "data_quality": "降级模式"
            }
        
        ensemble_result = self.predict_ensemble(stock_code, horizon)
        
        if "error" in ensemble_result:
            return ensemble_result
        
        # 计算技术指标
        prices = self.historical_data[stock_code].get("prices", [])
        
        # MA5 / MA10 / MA20
        ma5 = sum(prices[-5:]) / 5 if len(prices) >= 5 else prices[-1]
        ma10 = sum(prices[-10:]) / 10 if len(prices) >= 10 else prices[-1]
        ma20 = sum(prices[-20:]) / 20 if len(prices) >= 20 else prices[-1]
        
        # 波动率
        if HAS_NUMPY and len(prices) >= 20:
            volatility = np.std(prices[-20:]) / np.mean(prices[-20:]) * 100
        else:
            volatility = 0
        
        return {
            "stock_code": stock_code,
            "generated_at": datetime.now().isoformat(),
            "current_price": prices[-1] if prices else 0,
            "technical_indicators": {
                "ma5": round(ma5, 2),
                "ma10": round(ma10, 2),
                "ma20": round(ma20, 2),
                "volatility_20d": round(volatility, 2)
            },
            "prediction": ensemble_result,
            "recommendation": self._generate_recommendation(ensemble_result, ma5, ma10, ma20)
        }
    
    def _generate_recommendation(
        self, 
        prediction: Dict, 
        ma5: float, 
        ma10: float, 
        ma20: float
    ) -> str:
        """生成投资建议"""
        trend = prediction.get("trend", "unknown")
        confidence = prediction.get("confidence", "medium")
        
        # 均线信号
        ma_signal = "neutral"
        if ma5 > ma10 > ma20:
            ma_signal = "bullish"
        elif ma5 < ma10 < ma20:
            ma_signal = "bearish"
        
        # 综合判断
        if trend == "up" and ma_signal == "bullish" and confidence == "high":
            return "📈 看涨信号：预测上涨 + 均线多头排列 + 高置信度"
        elif trend == "down" and ma_signal == "bearish" and confidence == "high":
            return "📉 看跌信号：预测下跌 + 均线空头排列 + 高置信度"
        else:
            return "➡️ 观望：信号不明确或置信度较低"
    
    def batch_predict(self, stock_codes: List[str], horizon: int = 5) -> Dict:
        """
        批量预测
        
        Args:
            stock_codes: 股票代码列表
            horizon: 预测天数
        
        Returns:
            批量预测结果
        """
        results = {}
        for code in stock_codes:
            if code not in self.historical_data:
                self.load_data(code)
            results[code] = self.get_prediction_report(code, horizon)
        
        return {
            "generated_at": datetime.now().isoformat(),
            "horizon": horizon,
            "results": results
        }


def main():
    """测试预测引擎"""
    engine = PredictionEngine()
    
    # 加载测试数据
    test_stocks = ["sz002262"]  # 恒瑞医药
    
    for stock in test_stocks:
        engine.load_data(stock)
    
    # 生成预测报告
    report = engine.batch_predict(test_stocks, horizon=5)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
