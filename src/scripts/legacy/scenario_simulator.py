#!/usr/bin/env python3
"""
情景模拟器

使用 Monte Carlo 方法进行情景模拟：
1. 定义情景参数（价格、波动率、收益率）
2. 运行 Monte Carlo 模拟
3. 输出概率分布和风险指标
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# 尝试导入科学计算库
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("⚠️ numpy 未安装，使用简化模拟")


class ScenarioSimulator:
    """情景模拟器"""
    
    def __init__(self, n_simulations: int = 10000):
        self.n_simulations = n_simulations
        self.default_data_path = Path.home() / "obsidian" / "all about xia" / "data" / "stocks"
        
        # 路径预检
        self._validate_paths()
    
    def _validate_paths(self):
        """路径预检"""
        # 确保默认数据目录存在（不报错，只提示）
        if not self.default_data_path.exists():
            print(f"⚠️ 默认数据目录不存在: {self.default_data_path}")
            print("   请确保股票数据存放在该目录，或使用 data_path 参数指定路径")
    
    def monte_carlo_price(
        self,
        current_price: float,
        volatility: float,
        expected_return: float,
        days: int,
        risk_free_rate: float = 0.03
    ) -> Dict:
        """
        Monte Carlo 价格模拟
        
        Args:
            current_price: 当前价格
            volatility: 年化波动率
            expected_return: 预期年化收益率
            days: 模拟天数
            risk_free_rate: 无风险利率
        
        Returns:
            模拟结果
        """
        if HAS_NUMPY:
            import numpy as np
            
            # 转换为日度参数
            daily_return = expected_return / 252.0
            daily_vol = volatility / np.sqrt(252.0)
            
            # 模拟路径 - 使用向量化操作
            np.random.seed(42)  # 可重现
            
            # 生成所有随机冲击: (n_simulations, days)
            random_shocks = np.random.normal(0, 1, (self.n_simulations, days))
            
            # 计算对数收益率: (n_simulations, days)
            log_returns = (daily_return - 0.5 * daily_vol**2) + \
                         daily_vol * random_shocks
            
            # 计算累积对数价格: (n_simulations, days)
            cum_log_returns = np.cumsum(log_returns, axis=1)
            
            # 最终价格: (n_simulations,)
            final_prices = current_price * np.exp(cum_log_returns[:, -1])
            
            # 统计结果
            return {
                "method": "Monte Carlo (GBM)",
                "current_price": current_price,
                "simulations": self.n_simulations,
                "days": days,
                "final_price_stats": {
                    "mean": round(float(np.mean(final_prices)), 2),
                    "median": round(float(np.median(final_prices)), 2),
                    "std": round(float(np.std(final_prices)), 2),
                    "min": round(float(np.min(final_prices)), 2),
                    "max": round(float(np.max(final_prices)), 2)
                },
                "percentiles": {
                    "5": round(float(np.percentile(final_prices, 5)), 2),
                    "25": round(float(np.percentile(final_prices, 25)), 2),
                    "50": round(float(np.percentile(final_prices, 50)), 2),
                    "75": round(float(np.percentile(final_prices, 75)), 2),
                    "95": round(float(np.percentile(final_prices, 95)), 2)
                },
                "probability_gain": round(
                    float(np.mean(final_prices > current_price)) * 100, 1
                ),
                "probability_loss": round(
                    float(np.mean(final_prices < current_price)) * 100, 1
                )
            }
        else:
            # 简化版：随机游走
            import random
            daily_vol = volatility / math.sqrt(252)
            
            final_prices = []
            for _ in range(self.n_simulations):
                price = current_price
                for _ in range(days):
                    shock = random.gauss(0, 1)
                    price *= (1 + daily_vol * shock / 100)
                final_prices.append(price)
            
            final_prices.sort()
            
            return {
                "method": "Monte Carlo (简化)",
                "current_price": current_price,
                "simulations": self.n_simulations,
                "days": days,
                "final_price_stats": {
                    "mean": round(sum(final_prices) / len(final_prices), 2),
                    "min": round(min(final_prices), 2),
                    "max": round(max(final_prices), 2)
                },
                "percentiles": {
                    "5": round(final_prices[int(len(final_prices) * 0.05)], 2),
                    "50": round(final_prices[int(len(final_prices) * 0.5)], 2),
                    "95": round(final_prices[int(len(final_prices) * 0.95)], 2)
                }
            }
    
    def calculate_var(
        self,
        current_price: float,
        volatility: float,
        days: int,
        confidence_level: float = 0.95
    ) -> Dict:
        """
        计算 VaR (Value at Risk)
        
        Args:
            current_price: 当前价格
            volatility: 年化波动率
            days: 持有天数
            confidence_level: 置信水平
        
        Returns:
            VaR 结果
        """
        if HAS_NUMPY:
            daily_vol = volatility / math.sqrt(252)
            z_score = {0.90: 1.28, 0.95: 1.65, 0.99: 2.33}.get(confidence_level, 1.65)
            
            var_price = current_price * (1 - z_score * daily_vol * math.sqrt(days))
            var_amount = current_price - var_price
            var_percent = (var_amount / current_price) * 100
            
            return {
                "method": "VaR (参数法)",
                "current_price": current_price,
                "confidence_level": confidence_level,
                "days": days,
                "var_price": round(var_price, 2),
                "var_amount": round(var_amount, 2),
                "var_percent": round(var_percent, 2),
                "interpretation": f"在 {confidence_level*100:.0f}% 置信水平下，{days} 天内最大损失不超过 ¥{round(var_amount, 2)} ({round(var_percent, 2)}%)"
            }
        else:
            # 简化版
            daily_vol = volatility / math.sqrt(252)
            var_percent = 1.65 * daily_vol * math.sqrt(days) * 100
            
            return {
                "method": "VaR (简化)",
                "var_percent": round(var_percent, 2),
                "var_amount": round(current_price * var_percent / 100, 2)
            }
    
    def scenario_analysis(
        self,
        current_price: float,
        volatility: float,
        scenarios: Optional[List[Dict]] = None
    ) -> Dict:
        """
        情景分析
        
        Args:
            current_price: 当前价格
            volatility: 年化波动率
            scenarios: 情景列表 [{name, return_change, probability}]
        
        Returns:
            情景分析结果
        """
        if scenarios is None:
            # 默认情景
            scenarios = [
                {"name": "乐观", "return_change": 0.20, "probability": 0.2},
                {"name": "中性", "return_change": 0.0, "probability": 0.5},
                {"name": "悲观", "return_change": -0.20, "probability": 0.2},
                {"name": "极端悲观", "return_change": -0.40, "probability": 0.1}
            ]
        
        results = []
        expected_value = 0
        
        for scenario in scenarios:
            name = scenario["name"]
            change = scenario["return_change"]
            prob = scenario["probability"]
            
            target_price = current_price * (1 + change)
            expected_value += target_price * prob
            
            results.append({
                "name": name,
                "probability": prob,
                "return_change": change,
                "target_price": round(target_price, 2),
                "profit_loss": round(target_price - current_price, 2)
            })
        
        return {
            "current_price": current_price,
            "scenarios": results,
            "expected_value": round(expected_value, 2),
            "expected_return": round((expected_value - current_price) / current_price * 100, 2)
        }
    
    def generate_simulation_report(
        self,
        stock_code: str,
        current_price: float,
        volatility: float,
        horizon: int = 30
    ) -> Dict:
        """
        生成综合模拟报告
        
        Args:
            stock_code: 股票代码
            current_price: 当前价格
            volatility: 年化波动率
            horizon: 模拟天数
        
        Returns:
            模拟报告
        """
        # Monte Carlo 模拟
        mc_result = self.monte_carlo_price(
            current_price=current_price,
            volatility=volatility,
            expected_return=0.10,  # 假设 10% 预期收益
            days=horizon
        )
        
        # VaR 计算
        var_result = self.calculate_var(
            current_price=current_price,
            volatility=volatility,
            days=horizon,
            confidence_level=0.95
        )
        
        # 情景分析
        scenario_result = self.scenario_analysis(
            current_price=current_price,
            volatility=volatility
        )
        
        return {
            "stock_code": stock_code,
            "generated_at": datetime.now().isoformat(),
            "current_price": current_price,
            "volatility": volatility,
            "horizon_days": horizon,
            "monte_carlo": mc_result,
            "var": var_result,
            "scenario_analysis": scenario_result,
            "risk_summary": self._generate_risk_summary(mc_result, var_result)
        }
    
    def _generate_risk_summary(self, mc: Dict, var: Dict) -> str:
        """生成风险摘要"""
        prob_gain = mc.get("probability_gain", 50)
        var_percent = var.get("var_percent", 0)
        
        if prob_gain > 60 and var_percent < 10:
            return "✅ 风险较低：上涨概率高，最大损失可控"
        elif prob_gain < 40 and var_percent > 15:
            return "⚠️ 风险较高：下跌概率大，潜在损失较大"
        else:
            return "➡️ 风险中等：需结合其他因素判断"


def main():
    """测试情景模拟器"""
    simulator = ScenarioSimulator(n_simulations=1000)
    
    # 测试恒瑞医药
    report = simulator.generate_simulation_report(
        stock_code="sz002262",
        current_price=46.8,
        volatility=0.25,  # 25% 年化波动率
        horizon=30
    )
    
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
