#!/usr/bin/env python3
"""
风险预警器

检测异常波动并生成预警信号：
1. 异常波动检测（Z-score、滚动标准差）
2. 趋势反转检测
3. 预警信号生成
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

# 尝试导入科学计算库
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("⚠️ numpy 未安装，使用简化预警")


class RiskAlert:
    """风险预警器"""
    
    # 预警级别
    ALERT_LEVELS = {
        "critical": "🔴 严重",
        "high": "🟠 高",
        "medium": "🟡 中",
        "low": "🟢 低",
        "info": "🔵 提示"
    }
    
    def __init__(self):
        self.historical_data = {}
        self.alerts = []
        self.default_data_path = Path.home() / "obsidian" / "all about xia" / "data" / "stocks"
        
        # 路径预检
        self._validate_paths()
    
    def _validate_paths(self):
        """路径预检"""
        # 确保默认数据目录存在（不报错，只提示）
        if not self.default_data_path.exists():
            print(f"⚠️ 默认数据目录不存在: {self.default_data_path}")
            print("   请确保股票数据存放在该目录，或使用 data_path 参数指定路径")
    
    def load_data(self, stock_code: str, data_path: Optional[str] = None) -> bool:
        """加载历史价格数据"""
        if data_path:
            path = Path(data_path)
        else:
            path = Path.home() / "obsidian" / "all about xia" / "data" / "stocks" / f"{stock_code}.csv"
        
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
                
                self.historical_data[stock_code] = {
                    "dates": df[date_col].tolist(),
                    "prices": df[price_col].tolist()
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
                
                for line in data_lines[-100:]:
                    parts = line.strip().split(',')
                    if len(parts) >= 2:
                        try:
                            for i, p in enumerate(parts):
                                try:
                                    float(p)
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
            print(f"✅ 已加载 {stock_code}: {len(prices)} 条数据")
            return True
        except Exception as e:
            print(f"❌ 加载失败: {e}")
            return False
    
    def detect_anomaly_zscore(
        self, 
        stock_code: str, 
        window: int = 20,
        threshold: float = 2.0
    ) -> Dict:
        """
        Z-score 异常检测
        
        Args:
            stock_code: 股票代码
            window: 滚动窗口
            threshold: Z-score 阈值
        
        Returns:
            检测结果
        """
        if stock_code not in self.historical_data:
            return {"error": "数据未加载"}
        
        prices = self.historical_data[stock_code].get("prices", [])
        if len(prices) < window:
            return {"error": "数据不足"}
        
        if HAS_NUMPY:
            prices_array = np.array(prices[-window*2:])
            
            # 计算滚动 Z-score
            z_scores = []
            anomalies = []
            
            for i in range(window, len(prices_array)):
                window_prices = prices_array[i-window:i]
                mean = np.mean(window_prices)
                std = np.std(window_prices)
                
                if std > 0:
                    z = (prices_array[i] - mean) / std
                    z_scores.append(z)
                    
                    if abs(z) > threshold:
                        anomalies.append({
                            "index": i,
                            "price": round(float(prices_array[i]), 2),
                            "z_score": round(float(z), 2),
                            "direction": "up" if z > 0 else "down"
                        })
            
            current_z = z_scores[-1] if z_scores else 0
            
            return {
                "method": "Z-score",
                "window": window,
                "threshold": threshold,
                "current_z_score": round(current_z, 2),
                "anomaly_count": len(anomalies),
                "latest_anomaly": anomalies[-1] if anomalies else None,
                "status": "anomaly" if abs(current_z) > threshold else "normal"
            }
        else:
            # 简化版
            recent = prices[-window:]
            mean = sum(recent) / window
            std = (sum((x - mean)**2 for x in recent) / window) ** 0.5
            
            if std > 0:
                z = (prices[-1] - mean) / std
            else:
                z = 0
            
            return {
                "method": "Z-score (简化)",
                "current_z_score": round(z, 2),
                "status": "anomaly" if abs(z) > threshold else "normal"
            }
    
    def detect_trend_reversal(
        self, 
        stock_code: str, 
        short_window: int = 5,
        long_window: int = 20
    ) -> Dict:
        """
        趋势反转检测（均线交叉）
        
        Args:
            stock_code: 股票代码
            short_window: 短期均线窗口
            long_window: 长期均线窗口
        
        Returns:
            检测结果
        """
        if stock_code not in self.historical_data:
            return {"error": "数据未加载"}
        
        prices = self.historical_data[stock_code].get("prices", [])
        if len(prices) < long_window:
            return {"error": "数据不足"}
        
        # 计算均线
        ma_short = sum(prices[-short_window:]) / short_window
        ma_long = sum(prices[-long_window:]) / long_window
        
        # 前一期均线
        ma_short_prev = sum(prices[-short_window-1:-1]) / short_window if len(prices) > short_window else ma_short
        ma_long_prev = sum(prices[-long_window-1:-1]) / long_window if len(prices) > long_window else ma_long
        
        # 检测交叉
        reversal = None
        if ma_short > ma_long and ma_short_prev <= ma_long_prev:
            reversal = "golden_cross"  # 金叉
        elif ma_short < ma_long and ma_short_prev >= ma_long_prev:
            reversal = "death_cross"  # 死叉
        
        # 趋势强度
        trend_strength = (ma_short - ma_long) / ma_long * 100
        
        return {
            "method": "均线交叉",
            "ma_short": round(ma_short, 2),
            "ma_long": round(ma_long, 2),
            "ma_short_prev": round(ma_short_prev, 2),
            "ma_long_prev": round(ma_long_prev, 2),
            "reversal": reversal,
            "trend_strength": round(trend_strength, 2),
            "trend_direction": "up" if ma_short > ma_long else "down"
        }
    
    def detect_volatility_spike(
        self, 
        stock_code: str, 
        window: int = 10,
        threshold_factor: float = 2.0
    ) -> Dict:
        """
        波动率激增检测
        
        Args:
            stock_code: 股票代码
            window: 窗口
            threshold_factor: 阈值因子
        
        Returns:
            检测结果
        """
        if stock_code not in self.historical_data:
            return {"error": "数据未加载"}
        
        prices = self.historical_data[stock_code].get("prices", [])
        if len(prices) < window * 2:
            return {"error": "数据不足"}
        
        if HAS_NUMPY:
            prices_array = np.array(prices[-window*2:])
            
            # 计算滚动波动率
            recent_vol = np.std(prices_array[-window:]) / np.mean(prices_array[-window:])
            historical_vol = np.std(prices_array[:window]) / np.mean(prices_array[:window])
            
            vol_ratio = recent_vol / historical_vol if historical_vol > 0 else 1
            
            return {
                "method": "波动率比率",
                "recent_volatility": round(recent_vol * 100, 2),
                "historical_volatility": round(historical_vol * 100, 2),
                "vol_ratio": round(vol_ratio, 2),
                "threshold": threshold_factor,
                "status": "spike" if vol_ratio > threshold_factor else "normal"
            }
        else:
            # 简化版
            recent = prices[-window:]
            historical = prices[-window*2:-window]
            
            def calc_vol(p):
                mean = sum(p) / len(p)
                return (sum((x - mean)**2 for x in p) / len(p)) ** 0.5 / mean
            
            recent_vol = calc_vol(recent)
            historical_vol = calc_vol(historical)
            
            vol_ratio = recent_vol / historical_vol if historical_vol > 0 else 1
            
            return {
                "method": "波动率比率 (简化)",
                "vol_ratio": round(vol_ratio, 2),
                "status": "spike" if vol_ratio > threshold_factor else "normal"
            }
    
    def generate_alert(
        self, 
        stock_code: str, 
        current_price: float
    ) -> Dict:
        """
        生成综合预警
        
        Args:
            stock_code: 股票代码
            current_price: 当前价格
        
        Returns:
            预警报告
        """
        # 运行所有检测
        anomaly = self.detect_anomaly_zscore(stock_code)
        reversal = self.detect_trend_reversal(stock_code)
        volatility = self.detect_volatility_spike(stock_code)
        
        # 综合判断
        alerts = []
        severity_score = 0
        
        # Z-score 异常
        if anomaly.get("status") == "anomaly":
            z = abs(anomaly.get("current_z_score", 0))
            if z > 3:
                alerts.append({
                    "type": "异常波动",
                    "level": "critical",
                    "message": f"Z-score = {z:.2f}，价格显著偏离均值"
                })
                severity_score += 3
            elif z > 2:
                alerts.append({
                    "type": "异常波动",
                    "level": "high",
                    "message": f"Z-score = {z:.2f}，价格偏离均值"
                })
                severity_score += 2
        
        # 趋势反转
        if reversal.get("reversal") == "death_cross":
            alerts.append({
                "type": "趋势反转",
                "level": "high",
                "message": "死叉信号，短期均线下穿长期均线"
            })
            severity_score += 2
        elif reversal.get("reversal") == "golden_cross":
            alerts.append({
                "type": "趋势反转",
                "level": "info",
                "message": "金叉信号，短期均线上穿长期均线"
            })
        
        # 波动率激增
        if volatility.get("status") == "spike":
            ratio = volatility.get("vol_ratio", 1)
            alerts.append({
                "type": "波动率激增",
                "level": "medium" if ratio < 3 else "high",
                "message": f"波动率是历史均值的 {ratio:.1f} 倍"
            })
            severity_score += 2
        
        # 确定总体级别
        if severity_score >= 5:
            overall_level = "critical"
        elif severity_score >= 3:
            overall_level = "high"
        elif severity_score >= 1:
            overall_level = "medium"
        else:
            overall_level = "normal"
        
        return {
            "stock_code": stock_code,
            "current_price": current_price,
            "generated_at": datetime.now().isoformat(),
            "overall_level": overall_level,
            "overall_level_text": self.ALERT_LEVELS.get(overall_level, "正常"),
            "alerts": alerts,
            "severity_score": severity_score,
            "details": {
                "anomaly": anomaly,
                "reversal": reversal,
                "volatility": volatility
            },
            "recommendation": self._generate_recommendation(alerts, overall_level)
        }
    
    def _generate_recommendation(self, alerts: List[Dict], level: str) -> str:
        """生成建议"""
        if level == "critical":
            return "🚨 立即关注：多个严重信号，建议减仓或止损"
        elif level == "high":
            return "⚠️ 高度关注：存在风险信号，建议密切监控"
        elif level == "medium":
            return "📋 注意：有轻微异常，建议观察"
        elif level == "info":
            return "✅ 信号积极：趋势向好，可继续持有"
        else:
            return "➡️ 正常：无明显异常"
    
    def batch_alert(self, stock_codes: List[str]) -> Dict:
        """
        批量预警
        
        Args:
            stock_codes: 股票代码列表
        
        Returns:
            批量预警结果
        """
        results = {}
        for code in stock_codes:
            if code not in self.historical_data:
                self.load_data(code)
            
            prices = self.historical_data[code].get("prices", [])
            current_price = prices[-1] if prices else 0
            
            results[code] = self.generate_alert(code, current_price)
        
        # 统计
        level_counts = defaultdict(int)
        for code, result in results.items():
            level_counts[result["overall_level"]] += 1
        
        return {
            "generated_at": datetime.now().isoformat(),
            "total_stocks": len(stock_codes),
            "level_summary": dict(level_counts),
            "results": results
        }


def main():
    """测试风险预警器"""
    alert_system = RiskAlert()
    
    # 加载测试数据
    test_stocks = ["sz002262"]
    
    for stock in test_stocks:
        alert_system.load_data(stock)
    
    # 生成预警
    report = alert_system.batch_alert(test_stocks)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
