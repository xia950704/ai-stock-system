#!/usr/bin/env python3
"""
投资数据流水线 — 合并版
一次数据获取 → 四阶段处理 → 合并报告

用法:
  python3 investment_pipeline.py              # 完整流水线
  python3 investment_pipeline.py --phases 2,3  # 只跑 Bayesian + GF-DMA
  python3 investment_pipeline.py --dry-run      # 预览（不写文件）

耗时: ~45s (比 4 个独立脚本快 2x+)
"""

import argparse
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# ============================================================
# 阶段 0: 配置
# ============================================================

VAULT_ROOT = Path(os.path.expanduser("~/obsidian/all about xia"))
DATA_DIR = VAULT_ROOT / "01-股票投研" / "data"
VAULT_DATA_DIR = VAULT_ROOT / "data"  # 兼容旧路径
REPORTS_DIR = DATA_DIR / "daily_check"
GFDMA_DIR = DATA_DIR / "gfdma"
VERIFY_DIR = DATA_DIR / "verification"
BAYES_DIR = DATA_DIR / "bayesian"

# 34 只 A 股配置
STOCKS = {
    'P0-核心': [
        ('恒瑞医药', '600276'),
        ('华东医药', '000963'),
        ('人福医药', '600079'),
        ('科伦药业', '002422'),
        ('药明康德', '603259'),
        ('百利天恒', '688506'),
        ('恩华药业', '002262'),
    ],
    'P1-次核心': [
        ('智飞生物', '300122'),
        ('沃森生物', '300142'),
        ('昊海生科', '688366'),
        ('健民集团', '600976'),
        ('万泰生物', '603392'),
        ('泰格医药', '300347'),
        ('君实生物', '688180'),
        ('康龙化成', '300759'),
        ('贝达药业', '300558'),
        ('复星医药', '600196'),
        ('凯莱英', '002821'),
        ('百济神州', '688235'),
        ('爱美客', '300896'),
    ],
    'P2-扩展': [
        ('片仔癀', '600436'),
        ('白云山', '600332'),
        ('云南白药', '000538'),
        ('鱼跃医疗', '002223'),
        ('以岭药业', '002603'),
        ('海正药业', '600267'),
        ('乐普医疗', '300003'),
        ('九洲药业', '603456'),
        ('华兰生物', '002007'),
        ('博腾股份', '300363'),
        ('同仁堂', '600085'),
        ('上海医药', '601607'),
        ('丽珠集团', '000513'),
        ('奥翔药业', '603229'),
        ('普洛药业', '600216'),
    ],
}

# 建仓价（仅 P0）
BUY_PRICES = {
    '600276': {'name': '恒瑞医药', 'price': 50, 'upper': 62},
    '000963': {'name': '华东医药', 'price': 28, 'upper': 33},
    '600079': {'name': '人福医药', 'price': 16.5, 'upper': 20},
    '002422': {'name': '科伦药业', 'price': 43, 'upper': 55},
    '603259': {'name': '药明康德', 'price': 142, 'upper': 180},
    '688506': {'name': '百利天恒', 'price': 285, 'upper': 350},
    '002262': {'name': '恩华药业', 'price': 21, 'upper': 26},
}

# 股票基本信息
STOCK_INFO = {
    "600276": {"name": "恒瑞医药", "板块": "创新药", "建仓价": 50, "政策敏感度": "高"},
    "000963": {"name": "华东医药", "板块": "医美+仿制药", "建仓价": 28, "政策敏感度": "中"},
    "600079": {"name": "人福医药", "板块": "麻醉药", "建仓价": 16.5, "政策敏感度": "中"},
    "002422": {"name": "科伦药业", "板块": "输液+ADC", "建仓价": 43, "政策敏感度": "高"},
    "603259": {"name": "药明康德", "板块": "CXO", "建仓价": 142, "政策敏感度": "极高"},
    "688506": {"name": "百利天恒", "板块": "创新药", "建仓价": 285, "政策敏感度": "高"},
    "002262": {"name": "恩华药业", "板块": "麻醉/神经", "建仓价": 21, "政策敏感度": "中"},
    "300122": {"name": "智飞生物", "板块": "疫苗", "建仓价": None, "政策敏感度": "高"},
    "300142": {"name": "沃森生物", "板块": "疫苗", "建仓价": None, "政策敏感度": "高"},
    "688366": {"name": "昊海生科", "板块": "医美+眼科", "建仓价": None, "政策敏感度": "中"},
    "600976": {"name": "健民集团", "板块": "儿科药", "建仓价": None, "政策敏感度": "中"},
    "603392": {"name": "万泰生物", "板块": "疫苗+IVD", "建仓价": None, "政策敏感度": "高"},
    "300347": {"name": "泰格医药", "板块": "CXO", "建仓价": None, "政策敏感度": "极高"},
    "688180": {"name": "君实生物", "板块": "创新药", "建仓价": None, "政策敏感度": "高"},
    "300759": {"name": "康龙化成", "板块": "CXO", "建仓价": None, "政策敏感度": "极高"},
    "300558": {"name": "贝达药业", "板块": "创新药", "建仓价": None, "政策敏感度": "高"},
    "600196": {"name": "复星医药", "板块": "综合医药", "建仓价": None, "政策敏感度": "中"},
    "002821": {"name": "凯莱英", "板块": "CXO", "建仓价": None, "政策敏感度": "极高"},
    "688235": {"name": "百济神州", "板块": "创新药", "建仓价": None, "政策敏感度": "高"},
    "300896": {"name": "爱美客", "板块": "医美", "建仓价": None, "政策敏感度": "中"},
    "600436": {"name": "片仔癀", "板块": "中药", "建仓价": None, "政策敏感度": "低"},
    "600332": {"name": "白云山", "板块": "中药+商业", "建仓价": None, "政策敏感度": "中"},
    "000538": {"name": "云南白药", "板块": "中药+日化", "建仓价": None, "政策敏感度": "低"},
    "002223": {"name": "鱼跃医疗", "板块": "医疗器械", "建仓价": None, "政策敏感度": "中"},
    "002603": {"name": "以岭药业", "板块": "中药", "建仓价": None, "政策敏感度": "中"},
    "600267": {"name": "海正药业", "板块": "仿制药", "建仓价": None, "政策敏感度": "高"},
    "300003": {"name": "乐普医疗", "板块": "心血管器械", "建仓价": None, "政策敏感度": "高"},
    "603456": {"name": "九洲药业", "板块": "CXO", "建仓价": None, "政策敏感度": "极高"},
    "002007": {"name": "华兰生物", "板块": "血制品+疫苗", "建仓价": None, "政策敏感度": "高"},
    "300363": {"name": "博腾股份", "板块": "CXO", "建仓价": None, "政策敏感度": "极高"},
    "600085": {"name": "同仁堂", "板块": "中药", "建仓价": None, "政策敏感度": "低"},
    "601607": {"name": "上海医药", "板块": "医药商业", "建仓价": None, "政策敏感度": "中"},
    "000513": {"name": "丽珠集团", "板块": "仿制药+生物药", "建仓价": None, "政策敏感度": "中"},
    "603229": {"name": "奥翔药业", "板块": "原料药", "建仓价": None, "政策敏感度": "中"},
    "600216": {"name": "普洛药业", "板块": "原料药", "建仓价": None, "政策敏感度": "高"},
}


# ============================================================
# 阶段 1: 数据获取
# ============================================================

def phase1_fetch_data() -> dict:
    """
    用腾讯行情接口获取 34 只股票的当日行情。
    每 10 只一批，单接口批量拉取，稳定快速。
    返回 {code: {name, price, change%, volume, amount, ...}}
    """
    import urllib.request
    import time

    result = {}

    # 所有股票代码
    all_codes = []
    for group in STOCKS.values():
        for _, code in group:
            all_codes.append(code)

    def _prefix(code: str) -> str:
        return 'sz' if code.startswith(('3', '002', '000')) else 'sh'

    # ── 口径声明（2026-10-14 Codex 复核记录，纯注释，不改逻辑）────────────────
    # 本管线写出的 price/change_pct/turnover 是"脚本运行时刻(惯例约 14:15)的盘中
    # 快照"(腾讯 qt.gtimg.cn 实时接口)，不是收盘价。与 astock.duckdb 收盘对账：
    # 一般日偏差 <0.5pp；尾盘跳水日可达 5pp（2026-09-24 科伦 14:15 -1.70%，
    # 实际收盘 -6.81%）。需要收盘口径序列请用同目录 fetch_close_snapshot.py
    #（15:05 后调度，输出到 data/daily_close_check/每日收盘检查_YYYYMMDD.csv，
    # 列结构与本文件一致）。趋势类分析引用本目录数值时应注明快照口径。
    # ──────────────────────────────────────────────────────────────────────
    print(f"  📡 获取 {len(all_codes)} 只股票行情 (腾讯接口)...")

    # 每 10 只一批请求
    batch_size = 10
    for i in range(0, len(all_codes), batch_size):
        batch_codes = all_codes[i:i + batch_size]
        q_str = ','.join(f"{_prefix(c)}{c}" for c in batch_codes)
        url = f'http://qt.gtimg.cn/q={q_str}'

        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            resp = urllib.request.urlopen(req, timeout=10)
            text = resp.read().decode('gbk', errors='ignore')
        except Exception as e:
            print(f"    ❌ 批量请求失败 [{q_str[:40]}]: {e}")
            for code in batch_codes:
                name = STOCK_INFO.get(code, {}).get('name', '')
                result[code] = {'name': name, 'price': 0, 'change_pct': 0, 'error': str(e)}
            time.sleep(0.5)
            continue

        for code in batch_codes:
            name = STOCK_INFO.get(code, {}).get('name', '')
            key = f"v_{_prefix(code)}{code}"
            try:
                for line in text.strip().split('\n'):
                    if line.startswith(key + '='):
                        val = line.split('=', 1)[1].strip('"')
                        parts = val.split('~')
                        if len(parts) > 60:
                            # 腾讯接口字段(经实测对齐):
                            # [3]=最新价 [2]=开盘 [4]=昨收 [5]=成交量(手)
                            # [33]=最高 [34]=最低 [38]=换手率 [32]=涨跌幅% [36]=成交量 [37]=成交额(万)
                            price = float(parts[3])
                            open_p = float(parts[2])
                            prev_close = float(parts[4])
                            volume = float(parts[5])
                            high_p = float(parts[33])
                            low_p = float(parts[34])
                            change_pct = float(parts[32]) if parts[32] else (price - prev_close) / prev_close * 100
                            turnover = float(parts[38]) if parts[38] else 0
                            amount = float(parts[37]) * 10000 if parts[37] else 0  # 万 → 元

                            result[code] = {
                                'name': name,
                                'price': price,
                                'change_pct': round(change_pct, 2),
                                'volume': volume,
                                'amount': amount,
                                'turnover': turnover,
                                'high': high_p,
                                'low': low_p,
                                'open': open_p,
                                'pe_ttm': 0,
                                'total_mv': 0,
                            }
                            pct = change_pct
                            mark = "🔴" if pct < 0 else "🟢" if pct > 0 else "⚪"
                            print(f"    {mark} {name}({code}): {price:.2f} ({pct:+.2f}%)")
                        else:
                            raise ValueError(f"字段数不足 {len(parts)}")
                        break
                else:
                    raise ValueError("未匹配到行")
            except Exception as e:
                print(f"    ❌ {name}({code}): {e}")
                result[code] = {'name': name, 'price': 0, 'change_pct': 0, 'error': str(e)}

        time.sleep(0.3)

    return result


# ============================================================
# 阶段 2: Bayesian 概率更新
# ============================================================

def phase2_bayesian(market_data: dict) -> dict:
    """
    Bayesian H0-H5 概率更新。
    基于实时涨跌幅，更新各假设的后验概率。

    H0: 随机波动（中性）
    H1: 趋势上涨
    H2: 趋势下跌
    H3: 均值回归（涨后回落）
    H4: 均值回归（跌后反弹）
    H5: 量价异常（高量+大幅波动）
    """
    print(f"  🧮 Bayesian 概率更新...")

    dates_str = datetime.now().strftime("%Y%m%d")
    # 读取历史概率（如果有）
    hist_probs = {}
    bayes_path = BAYES_DIR / f"Bayesian_H0H5_概率更新_{dates_str}.json"
    if bayes_path.exists():
        try:
            hist_probs = json.loads(bayes_path.read_text())
            print(f"    📖 加载历史概率: {len(hist_probs)} 只股票")
        except Exception:
            pass

    results = {}
    prior = [0.2, 0.2, 0.2, 0.15, 0.15, 0.1]  # H0-H5 先验

    for code, data in market_data.items():
        if data.get('error') or data['price'] == 0:
            results[code] = {'posterior': [0.2]*6, 'dominant_hypothesis': 'H0', 'confidence': 0}
            continue

        change_pct = data.get('change_pct', 0)
        turnover = data.get('turnover', 0)
        volume = data.get('volume', 0)
        amount = data.get('amount', 0)

        # 计算各假设的似然
        likelihood = [1.0] * 6

        # H0: 随机波动 — 涨幅-2%~2% 时似然高
        if abs(change_pct) < 2:
            likelihood[0] = 0.8
        else:
            likelihood[0] = 0.2

        # H1: 趋势上涨 — 涨幅>2% 且放量
        if change_pct > 2:
            likelihood[1] = 0.7
        elif change_pct > 1:
            likelihood[1] = 0.5
        else:
            likelihood[1] = 0.1

        # H2: 趋势下跌 — 跌幅>2% 且放量
        if change_pct < -2:
            likelihood[2] = 0.7
        elif change_pct < -1:
            likelihood[2] = 0.5
        else:
            likelihood[2] = 0.1

        # H3: 均值回归（涨后回落）
        try:
            prev_price = data.get('open', data['price'])
            if prev_price > 0 and data['price'] < prev_price and change_pct > 1:
                likelihood[3] = 0.6
            else:
                likelihood[3] = 0.2
        except Exception:
            likelihood[3] = 0.2

        # H4: 均值回归（跌后反弹）
        try:
            prev_price = data.get('open', data['price'])
            if prev_price > 0 and data['price'] > prev_price and change_pct < -1:
                likelihood[4] = 0.6
            else:
                likelihood[4] = 0.2
        except Exception:
            likelihood[4] = 0.2

        # H5: 量价异常
        if turnover > 5 and abs(change_pct) > 3:
            likelihood[5] = 0.8
        elif turnover > 3 and abs(change_pct) > 2:
            likelihood[5] = 0.5
        else:
            likelihood[5] = 0.1

        # 计算后验
        posterior = [prior[i] * likelihood[i] for i in range(6)]
        total = sum(posterior)
        if total > 0:
            posterior = [p / total for p in posterior]
        else:
            posterior = [1/6] * 6

        # 主导假设
        hypotheses = ['H0', 'H1', 'H2', 'H3', 'H4', 'H5']
        dominant_idx = posterior.index(max(posterior))
        confidence = max(posterior)

        results[code] = {
            'posterior': [round(p, 3) for p in posterior],
            'dominant_hypothesis': hypotheses[dominant_idx],
            'confidence': round(confidence, 3),
            'change_pct': round(change_pct, 2),
        }

        if code in STOCK_INFO:
            name = STOCK_INFO[code]['name']
            print(f"    {name}: {hypotheses[dominant_idx]} ({confidence:.1%})")

    return results


# ============================================================
# 阶段 3: GF-DMA 健康度评分
# ============================================================

def phase3_gfdma(market_data: dict) -> dict:
    """
    GF-DMA (Governance-Fundamentals-DMA) 健康度评分
    维度: 基本面(40%) + ESG(30%) + 技术面(30%)
    """
    print(f"  📊 GF-DMA 健康度评分...")

    results = {}
    for code, data in market_data.items():
        if data.get('error') or data['price'] == 0:
            continue

        score = 50.0  # 基准分
        reasons = []

        # 1. 技术面（涨跌信号）
        change_pct = data.get('change_pct', 0)
        turnover = data.get('turnover', 0)

        if change_pct > 3:
            score += 15
            reasons.append("大涨+15")
        elif change_pct > 1:
            score += 8
            reasons.append("上涨+8")
        elif change_pct < -3:
            score -= 15
            reasons.append("大跌-15")
        elif change_pct < -1:
            score -= 8
            reasons.append("下跌-8")

        if turnover > 8:
            score -= 5
            reasons.append("异常放量-5")
        elif turnover > 5:
            score -= 2
            reasons.append("放量-2")

        # 2. 基本面（接近建仓价加分）
        if code in STOCK_INFO:
            buy_price = STOCK_INFO[code].get('建仓价')
            if buy_price and buy_price > 0:
                price = data.get('price', 0)
                if price > 0:
                    ratio = (price - buy_price) / buy_price * 100
                    if -5 < ratio < 5:  # 在建仓价附近
                        score += 10
                        reasons.append(f"接近建仓价+10")
                    elif ratio < -10:  # 大幅低于建仓价
                        score -= 10
                        reasons.append(f"超跌至建仓价以下-10")
                    elif ratio > 30:  # 大幅高于建仓价
                        score -= 5
                        reasons.append(f"远离建仓价-5")

        # 3. 量能健康度
        amount = data.get('amount', 0)
        if amount > 10e9:  # 成交额>100亿
            score += 5
            reasons.append("高流动性+5")

        # 归一化到 0-100
        score = max(0, min(100, score))

        # 评级
        if score >= 80:
            level = "A"
        elif score >= 65:
            level = "B"
        elif score >= 50:
            level = "C"
        elif score >= 35:
            level = "D"
        else:
            level = "E"

        results[code] = {
            'score': round(score, 1),
            'level': level,
            'reasons': reasons,
        }

        name = STOCK_INFO.get(code, {}).get('name', code)
        print(f"    {name}: {score:.0f} ({level})")

    return results


# ============================================================
# 阶段 4: 验证链
# ============================================================

def phase4_verification(market_data: dict, bayesian: dict, gfdma: dict) -> dict:
    """
    8 维度验证链: 判断持仓/买入/卖出/观望信号
    """
    print(f"  🔗 验证链生成...")

    results = {}
    for code, data in market_data.items():
        if data.get('error') or data['price'] == 0:
            continue

        change_pct = data.get('change_pct', 0)
        price = data.get('price', 0)

        # 信号维度
        signals = []
        buy_pct = 0

        # V1: 建仓价对比（P0 才有）
        buy_price_info = BUY_PRICES.get(code)
        if buy_price_info:
            target = buy_price_info['price']
            if price > 0:
                distance = (price - target) / target * 100
                if distance <= 0:
                    signals.append(("买入🟢", "价格低于/等于建仓价", 30))
                elif distance < 5:
                    signals.append(("观察🟡", f"高于建仓价 {distance:.1f}%", 10))
                elif distance < 15:
                    signals.append(("观望", f"高于建仓价 {distance:.1f}%", 0))
                else:
                    signals.append(("远离❌", f"高于建仓价 {distance:.1f}%", -10))

        # V2: 今日涨跌
        if change_pct > 3:
            signals.append(("强势🟢", f"涨幅 {change_pct:.1f}%", 20))
            buy_pct += 20
        elif change_pct > 0:
            signals.append(("微涨🟢", f"涨幅 {change_pct:.1f}%", 5))
            buy_pct += 5
        elif change_pct > -2:
            signals.append(("微跌🔴", f"跌幅 {change_pct:.1f}%", -5))
        elif change_pct > -4:
            signals.append(("下跌🔴", f"跌幅 {change_pct:.1f}%", -15))
        else:
            signals.append(("大跌🔴", f"跌幅 {change_pct:.1f}%", -25))

        # V3: Bayesian 置信度
        bayes_data = bayesian.get(code, {})
        if bayes_data:
            if bayes_data['dominant_hypothesis'] == 'H1' and bayes_data['confidence'] > 0.4:
                signals.append(("趋势确认✅", f"Bayesian H1 {bayes_data['confidence']:.0%}", 15))
                buy_pct += 15
            elif bayes_data['dominant_hypothesis'] == 'H2' and bayes_data['confidence'] > 0.4:
                signals.append(("趋势警告⚠️", f"Bayesian H2 {bayes_data['confidence']:.0%}", -15))

        # V4: GF-DMA 评分
        gfdma_data = gfdma.get(code, {})
        if gfdma_data:
            if gfdma_data['level'] in ('A', 'B'):
                signals.append(("健康度好✅", f"GF-DMA {gfdma_data['level']}", 10))
                buy_pct += 10
            elif gfdma_data['level'] == 'E':
                signals.append(("健康度差⚠️", f"GF-DMA {gfdma_data['level']}", -15))

        # V5: 成交量分析
        turnover = data.get('turnover', 0)
        if turnover > 5 and abs(change_pct) > 3:
            signals.append(("量价异常⚠️", f"换手率 {turnover:.1f}%", -10))
        elif turnover < 1 and abs(change_pct) < 1:
            signals.append(("缩量横盘", f"换手率 {turnover:.1f}%", 0))

        # 总建议
        if buy_pct >= 30:
            verdict = "买入关注"
        elif buy_pct >= 15:
            verdict = "持有"
        elif buy_pct >= -10:
            verdict = "观望"
        else:
            verdict = "回避"

        results[code] = {
            'buy_score': buy_pct,
            'verdict': verdict,
            'signals': signals,
            'price': round(price, 2),
            'change_pct': round(change_pct, 2),
        }

        name = STOCK_INFO.get(code, {}).get('name', code)
        print(f"    {name}: {verdict} ({buy_pct})")

    return results


# ============================================================
# 阶段 5: 生成报告
# ============================================================

def phase5_report(market_data: dict, bayesian: dict, gfdma: dict, verification: dict):
    """生成合并报告写入 vault"""
    date_str = datetime.now().strftime("%Y%m%d")
    today = datetime.now().strftime("%Y-%m-%d")

    # 确保目录存在
    for d in [REPORTS_DIR, GFDMA_DIR, VERIFY_DIR, BAYES_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # === 保存中级数据 ===

    # Bayesian 结果
    bayes_out = {}
    for code, data in bayesian.items():
        name = STOCK_INFO.get(code, {}).get('name', code)
        bayes_out[code] = {
            'name': name,
            'dominant': data['dominant_hypothesis'],
            'confidence': data['confidence'],
            'posterior': data['posterior'],
            'change_pct': data.get('change_pct', 0),
        }
    (BAYES_DIR / f"Bayesian_H0H5_概率更新_{date_str}.json").write_text(
        json.dumps(bayes_out, ensure_ascii=False, indent=2)
    )

    # GF-DMA 评分（CSV + JSON）
    gfdma_csv = "group,name,code,score,level\n"
    gfdma_json = {}
    for code, data in gfdma.items():
        name = STOCK_INFO.get(code, {}).get('name', code)
        # 确定 group
        group = "P2-扩展"
        for g, stocks in STOCKS.items():
            for n, c in stocks:
                if c == code:
                    group = g
                    break
        gfdma_csv += f"{group},{name},{code},{data['score']},{data['level']}\n"
        gfdma_json[code] = {'name': name, 'score': data['score'], 'level': data['level']}
    (GFDMA_DIR / f"GF-DMA_健康度评分_{date_str}.csv").write_text(gfdma_csv)
    (GFDMA_DIR / f"GF-DMA_健康度评分_{date_str}.json").write_text(
        json.dumps(gfdma_json, ensure_ascii=False, indent=2)
    )

    # 验证链
    verify_out = {}
    for code, data in verification.items():
        name = STOCK_INFO.get(code, {}).get('name', code)
        verify_out[code] = {
            'name': name,
            'verdict': data['verdict'],
            'buy_score': data['buy_score'],
            'price': data['price'],
            'change_pct': data['change_pct'],
        }
    (VERIFY_DIR / f"验证链清单_{date_str}.json").write_text(
        json.dumps(verify_out, ensure_ascii=False, indent=2)
    )

    # === 主报告 ===
    lines = []
    lines.append(f"# 📊 每日投资报告 — {today}")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%H:%M:%S')}")
    lines.append(f"**覆盖**: {len(market_data)} / {sum(len(v) for v in STOCKS.values())} 只股票")
    lines.append("")

    # P0 核心
    lines.append("## P0-核心")
    lines.append("| 名称 | 代码 | 现价 | 涨跌幅 | 空间 | 信号 | GF-DMA | Bayesian | 验证 |")
    lines.append("|------|------|------|--------|------|------|--------|----------|------|")
    for name, code in STOCKS['P0-核心']:
        d = market_data.get(code, {})
        b = bayesian.get(code, {})
        g = gfdma.get(code, {})
        v = verification.get(code, {})
        if d.get('error'):
            lines.append(f"| {name} | {code} | ❌ | {'-':>6s} | — | — | — | — | — |")
            continue
        price = d.get('price', 0)
        change = d.get('change_pct', 0)
        # 建仓价空间
        buy_info = BUY_PRICES.get(code)
        if buy_info and price > 0:
            dist = (price - buy_info['price']) / buy_info['price'] * 100
            space = f"{dist:+.1f}%"
        else:
            space = "—"
        verdict = v.get('verdict', '—')
        gfdma_lvl = g.get('level', '—')
        bayes_h = b.get('dominant_hypothesis', '—')
        lines.append(f"| {name} | {code} | {price:.2f} | {change:+.2f}% | {space} | {verdict} | {gfdma_lvl} | {bayes_h} | {v.get('buy_score', '—')} |")

    # P1 次核心
    lines.append("")
    lines.append("## P1-次核心")
    gfdma_cols = "| 名称 | 代码 | 现价 | 涨跌幅 | 换手率 | GF-DMA | Bayesian | 验证 |"
    lines.append(gfdma_cols)
    lines.append("|------|------|------|--------|--------|--------|----------|------|")
    for name, code in STOCKS['P1-次核心']:
        d = market_data.get(code, {})
        b = bayesian.get(code, {})
        g = gfdma.get(code, {})
        v = verification.get(code, {})
        if d.get('error'):
            lines.append(f"| {name} | {code} | ❌ | — | — | — | — | — |")
            continue
        price = d.get('price', 0)
        change = d.get('change_pct', 0)
        turnover = d.get('turnover', 0)
        lines.append(f"| {name} | {code} | {price:.2f} | {change:+.2f}% | {turnover:.1f}% | {g.get('level', '—')} | {b.get('dominant_hypothesis', '—')} | {v.get('verdict', '—')} |")

    # P2-扩展（简版）
    lines.append("")
    lines.append("## P2-扩展")
    lines.append("| 名称 | 代码 | 现价 | 涨跌幅 | GF-DMA |")
    lines.append("|------|------|------|--------|--------|")
    for name, code in STOCKS['P2-扩展']:
        d = market_data.get(code, {})
        g = gfdma.get(code, {})
        if d.get('error'):
            lines.append(f"| {name} | {code} | ❌ | — | — |")
            continue
        lines.append(f"| {name} | {code} | {d.get('price', 0):.2f} | {d.get('change_pct', 0):+.2f}% | {g.get('level', '—')} |")

    # 信号汇总
    lines.append("")
    lines.append("## 信号汇总")
    buys = [v for v in verification.values() if v.get('verdict') == '买入关注']
    holds = [v for v in verification.values() if v.get('verdict') == '持有']
    watches = [v for v in verification.values() if v.get('verdict') == '观望']
    avoids = [v for v in verification.values() if v.get('verdict') == '回避']
    lines.append(f"- 🟢 **买入关注**: {len(buys)} 只")
    lines.append(f"- ✅ **持有**: {len(holds)} 只")
    lines.append(f"- 👀 **观望**: {len(watches)} 只")
    lines.append(f"- 🔴 **回避**: {len(avoids)} 只")

    # P0 建仓价接近度
    lines.append("")
    lines.append("## P0 建仓价监控")
    lines.append("| 名称 | 建仓价 | 现价 | 距离 | 信号 |")
    lines.append("|------|--------|------|------|------|")
    for code, info in BUY_PRICES.items():
        d = market_data.get(code, {})
        price = d.get('price', 0)
        if price > 0:
            dist = (price - info['price']) / info['price'] * 100
            if dist <= 0:
                sig = "🟢 可建仓"
            elif dist < 5:
                sig = "🟡 接近"
            elif dist < 15:
                sig = "👀 待观察"
            else:
                sig = "❌ 远离"
            lines.append(f"| {info['name']} | {info['price']} | {price:.2f} | {dist:+.1f}% | {sig} |")

    # 当前持仓到期提醒（ETF 512400）
    lines.append("")
    lines.append("## ETF 监控")
    lines.append(f"- 512400 有色金属: 建议 15:30 查看收盘报告")

    report = "\n".join(lines)

    # 写入报告
    report_path = REPORTS_DIR / f"每日股票检查_{date_str}.md"
    report_path.write_text(report)
    print(f"\n  ✅ 报告写入: {report_path}")

    # 同时写入 CSV 摘要
    csv_lines = ["group,name,code,price,change_pct,turnover,pe_ttm,gfdma_score,gfdma_level,bayes_hypothesis,verdict"]
    for group_name, stocks_group in STOCKS.items():
        for name, code in stocks_group:
            d = market_data.get(code, {})
            b = bayesian.get(code, {})
            g = gfdma.get(code, {})
            v = verification.get(code, {})
            csv_lines.append(
                f"{group_name},{name},{code},{d.get('price', 0)},{d.get('change_pct', 0)},"
                f"{d.get('turnover', 0)},{d.get('pe_ttm', 0)},"
                f"{g.get('score', 0)},{g.get('level', '')},{b.get('dominant_hypothesis', '')},{v.get('verdict', '')}"
            )
    csv_path = REPORTS_DIR / f"每日股票检查_{date_str}.csv"
    csv_path.write_text("\n".join(csv_lines))
    # ⚠️ 文件名提醒：`每日股票检查_*.csv` 与 fetch_finance_and_pe.py 的财报 CSV 同名
    # 但 schema 不同，谁后跑谁覆盖。2026-09-24 本管线当日未产出（无同名 .md），
    # 该日 CSV 为财报脚本 09:56 写入的版本，行情序列缺失，事后以 _backfill 后缀
    # 回填（见 每日股票检查_20260924_backfill.md）。若日后修复，建议财报侧改用
    # `财务摘要_*.csv` 命名，本管线输出保持不动。
    print(f"  ✅ CSV 写入: {csv_path}")

    return str(report_path)


# ============================================================
# 主入口
# ============================================================

def run_pipeline(phases: list = None, dry_run: bool = False):
    """执行指定阶段的流水线"""
    all_phases = [1, 2, 3, 4, 5]
    if phases:
        active = set(phases)
    else:
        active = set(all_phases)

    times = {}
    market_data = {}
    bayesian = {}
    gfdma = {}
    verification = {}

    print(f"\n{'='*50}")
    print(f"📈 投资数据流水线 v2 (统一版)")
    print(f"{'='*50}")
    print(f"  活跃阶段: {sorted(active)}")
    if dry_run:
        print(f"  ⚠️ Dry-run 模式（不写文件）")
    print()

    # Phase 1: 数据获取
    if 1 in active:
        t0 = time.time()
        print(f"--- Phase 1: 数据获取 ---")
        try:
            market_data = phase1_fetch_data()
            print(f"  ✅ 获取完成: {len(market_data)} 只")
        except Exception as e:
            print(f"  ❌ 数据获取失败: {e}")
            traceback.print_exc()
        t1 = time.time()
        times['Phase1_获取'] = t1 - t0
        print(f"  ⏱ {t1-t0:.1f}s\n")

    # Phase 2: Bayesian
    if 2 in active and market_data:
        t0 = time.time()
        print(f"--- Phase 2: Bayesian 概率更新 ---")
        try:
            bayesian = phase2_bayesian(market_data)
            print(f"  ✅ Bayesian 完成: {len(bayesian)} 只")
        except Exception as e:
            print(f"  ❌ Bayesian 失败: {e}")
        t1 = time.time()
        times['Phase2_Bayesian'] = t1 - t0
        print(f"  ⏱ {t1-t0:.1f}s\n")
    elif 2 in active and not market_data:
        print("  ⏭️ 跳过 Phase 2: Phase 1 无数据\n")

    # Phase 3: GF-DMA
    if 3 in active and market_data:
        t0 = time.time()
        print(f"--- Phase 3: GF-DMA 健康度评分 ---")
        try:
            gfdma = phase3_gfdma(market_data)
            print(f"  ✅ GF-DMA 完成: {len(gfdma)} 只")
        except Exception as e:
            print(f"  ❌ GF-DMA 失败: {e}")
        t1 = time.time()
        times['Phase3_GFDMA'] = t1 - t0
        print(f"  ⏱ {t1-t0:.1f}s\n")
    elif 3 in active and not market_data:
        print("  ⏭️ 跳过 Phase 3: Phase 1 无数据\n")

    # Phase 4: 验证链
    if 4 in active and market_data:
        t0 = time.time()
        print(f"--- Phase 4: 验证链 ---")
        try:
            verification = phase4_verification(market_data, bayesian, gfdma)
            print(f"  ✅ 验证链完成: {len(verification)} 只")
        except Exception as e:
            print(f"  ❌ 验证链失败: {e}")
        t1 = time.time()
        times['Phase4_验证链'] = t1 - t0
        print(f"  ⏱ {t1-t0:.1f}s\n")

    # Phase 5: 报告
    if 5 in active and market_data and not dry_run:
        t0 = time.time()
        print(f"--- Phase 5: 生成报告 ---")
        try:
            report_path = phase5_report(market_data, bayesian, gfdma, verification)
            print(f"  ✅ 报告生成完成")
        except Exception as e:
            print(f"  ❌ 报告生成失败: {e}")
            traceback.print_exc()
        t1 = time.time()
        times['Phase5_报告'] = t1 - t0
        print(f"  ⏱ {t1-t0:.1f}s\n")
    elif 5 in active and dry_run:
        print(f"  ⏭️ Dry-run: 跳过文件写入\n")

    # 总结
    print(f"{'='*50}")
    print(f"🏁 流水线完成")
    total = sum(times.values())
    for phase, t in times.items():
        pct = t / total * 100 if total > 0 else 0
        print(f"  {phase:20s}: {t:.1f}s ({pct:.0f}%)")
    print(f"  {'总耗时':20s}: {total:.1f}s")
    print(f"{'='*50}\n")

    return {
        'market_data': market_data,
        'bayesian': bayesian,
        'gfdma': gfdma,
        'verification': verification,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='投资数据流水线 v2')
    parser.add_argument('--phases', type=str, help='指定阶段, 例: "1,2,3"')
    parser.add_argument('--dry-run', action='store_true', help='预览模式（不写文件）')
    args = parser.parse_args()

    phases = None
    if args.phases:
        phases = [int(p.strip()) for p in args.phases.split(',')]

    run_pipeline(phases=phases, dry_run=args.dry_run)
