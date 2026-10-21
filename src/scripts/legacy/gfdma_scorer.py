#!/usr/bin/env python3
"""
GF-DMA 健康度评分脚本（混合版）
使用实时价格 + 财务数据估算技术面指标
不再依赖历史 K 线数据
"""

import pandas as pd
import json
import sys
from datetime import datetime
from pathlib import Path

# 输出目录
OUTPUT_DIR = Path("/Users/xiashuang/obsidian/all about xia/01-股票投研/data")

# 34 只 A 股配置
STOCKS = {
    'P0-核心': [
        ('恒瑞医药', '600276'),
        ('华东医药', '000963'),
        ('人福医药', '600079'),
        ('科伦药业', '002422'),
        ('药明康德', '603259'),
        ('百利天恒', '688506'),
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

# 加载 PE 数据
def load_pe_data(date_str: str) -> dict:
    """加载 PE 数据"""
    pe_path = OUTPUT_DIR / f"pe_data_{date_str}.json"
    if pe_path.exists():
        with open(pe_path) as f:
            data = json.load(f)
            return data.get('pe_data', {})
    return {}

# 加载实时价格数据
def load_price_data(date_str: str) -> dict:
    """加载实时价格数据"""
    price_path = OUTPUT_DIR / f"price_data_{date_str}.json"
    if price_path.exists():
        with open(price_path) as f:
            data = json.load(f)
            return data.get('price_data', {})
    return {}

# 加载财务数据
def load_finance_data(date_str: str) -> dict:
    """加载财务数据"""
    csv_path = OUTPUT_DIR / "daily_check" / f"每日股票检查_{date_str}.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        return {row['代码']: row for _, row in df.iterrows()}
    return {}


def calculate_gfdma_score(code: str, price_data: dict, pe_data: dict, finance_data: dict) -> dict:
    """
    计算 GF-DMA 健康度评分（混合版）
    
    评分维度：
    1. 价格趋势 (25%) - 使用涨跌幅 + 量比
    2. 动量指标 (25%) - 使用涨跌幅
    3. 量价配合 (15%) - 使用量比 × 涨跌幅
    4. 估值位置 (20%) - 使用 PE 分位
    5. 基本面 (15%) - 使用营收增速 + 利润增速 + ROE
    """
    
    # 获取数据
    price = price_data.get(code) if code in price_data else None
    pe = pe_data.get(code)
    finance = finance_data.get(code)
    
    scores = {}
    
    # 1. 价格趋势 (25%) - 基于涨跌幅和量比
    if price and price.get('success'):
        change_pct = price.get('change_pct', 0) or 0
        volume = price.get('volume', 0) or 0
        
        # 涨跌幅得分 (0-100)
        # >5%: 100, 2-5%: 80, 0-2%: 60, -2-0%: 40, <-2%: 20
        if change_pct > 5:
            trend_score = 100
        elif change_pct > 2:
            trend_score = 80
        elif change_pct > 0:
            trend_score = 60
        elif change_pct > -2:
            trend_score = 40
        else:
            trend_score = 20
        
        scores['价格趋势'] = trend_score
    else:
        scores['价格趋势'] = 50  # 默认中性
    
    # 2. 动量指标 (25%) - 基于涨跌幅
    if price and price.get('success'):
        change_pct = price.get('change_pct', 0) or 0
        
        # 动量得分 (0-100)
        # 与价格趋势类似，但更强调持续性
        if change_pct > 5:
            momentum_score = 100
        elif change_pct > 2:
            momentum_score = 80
        elif change_pct > 0:
            momentum_score = 60
        elif change_pct > -2:
            momentum_score = 40
        else:
            momentum_score = 20
        
        scores['动量'] = momentum_score
    else:
        scores['动量'] = 50
    
    # 3. 量价配合 (15%) - 量比 × 涨跌幅
    if price and price.get('success'):
        change_pct = price.get('change_pct', 0) or 0
        volume = price.get('volume', 0) or 0
        
        # 量价配合得分 (0-100)
        # 量价齐升: 高分, 量价背离: 低分
        if change_pct > 0 and volume > 1000000:  # 放量上涨
            volume_score = 90
        elif change_pct > 0 and volume > 0:  # 缩量上涨
            volume_score = 70
        elif change_pct < 0 and volume > 1000000:  # 放量下跌
            volume_score = 30
        elif change_pct < 0 and volume > 0:  # 缩量下跌
            volume_score = 50
        else:
            volume_score = 50
        
        scores['量价配合'] = volume_score
    else:
        scores['量价配合'] = 50
    
    # 4. 估值位置 (20%) - PE 分位
    if pe is not None:
        # PE 分位评分 (0-100)
        # PE < 15: 低估 (80-100), PE 15-25: 合理 (50-80), PE 25-40: 偏高 (30-50), PE > 40: 高估 (0-30)
        if pe < 15:
            pe_score = 90
        elif pe < 25:
            pe_score = 70
        elif pe < 40:
            pe_score = 50
        elif pe < 60:
            pe_score = 30
        else:
            pe_score = 10
        
        scores['估值位置'] = pe_score
    else:
        scores['估值位置'] = 50  # 默认中性
    
    # 5. 基本面 (15%) - 营收增速 + 利润增速 + ROE
    if finance:
        rev_growth = finance.get('营收增速(%)', 0) or 0
        profit_growth = finance.get('利润增速(%)', 0) or 0
        roe = finance.get('ROE(%)', 0) or 0
        
        # 基本面得分 (0-100)
        # 双增长 + 高 ROE: 高分, 双降 + 低 ROE: 低分
        base_score = 50
        
        if rev_growth > 10:
            base_score += 15
        elif rev_growth > 0:
            base_score += 5
        elif rev_growth < -10:
            base_score -= 15
        elif rev_growth < 0:
            base_score -= 5
        
        if profit_growth > 10:
            base_score += 15
        elif profit_growth > 0:
            base_score += 5
        elif profit_growth < -10:
            base_score -= 15
        elif profit_growth < 0:
            base_score -= 5
        
        if roe > 15:
            base_score += 10
        elif roe > 10:
            base_score += 5
        elif roe < 5:
            base_score -= 10
        elif roe < 10:
            base_score -= 5
        
        scores['基本面'] = max(0, min(100, base_score))
    else:
        scores['基本面'] = 50
    
    # 计算综合评分
    weights = {
        '价格趋势': 0.25,
        '动量': 0.25,
        '量价配合': 0.15,
        '估值位置': 0.20,
        '基本面': 0.15,
    }
    
    total_score = sum(scores[k] * weights[k] for k in scores)
    
    # 健康度等级
    if total_score >= 70:
        level = '🟢 强势'
    elif total_score >= 40:
        level = '🟡 中性'
    else:
        level = '🔴 弱势'
    
    return {
        '代码': code,
        '综合评分': round(total_score, 1),
        '健康度': level,
        '价格趋势': scores['价格趋势'],
        '动量': scores['动量'],
        '量价配合': scores['量价配合'],
        '估值位置': scores['估值位置'],
        '基本面': scores['基本面'],
        'PE_TTM': pe,
        '涨跌幅(%)': price.get('change_pct') if price else None,
    }


def generate_report(results: list, date_str: str) -> str:
    """生成 GF-DMA 健康度评分 Markdown 报告"""
    
    # 统计
    strong = [r for r in results if '🟢' in r['健康度']]
    neutral = [r for r in results if '🟡' in r['健康度']]
    weak = [r for r in results if '🔴' in r['健康度']]
    
    report = f"""# GF-DMA 健康度评分 - {date_str}

**评分时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**评分股票：** {len(results)} 只
**数据来源：** 腾讯财经实时价格 + Akshare 财务数据

---

## 评分说明

**评分维度：**
| 维度 | 权重 | 说明 |
|------|------|------|
| 价格趋势 | 25% | 基于涨跌幅和量比 |
| 动量 | 25% | 基于涨跌幅持续性 |
| 量价配合 | 15% | 量比 × 涨跌幅 |
| 估值位置 | 20% | PE 分位评分 |
| 基本面 | 15% | 营收增速 + 利润增速 + ROE |

**健康度等级：**
- 🟢 强势 (70-100 分)
- 🟡 中性 (40-69 分)
- 🔴 弱势 (0-39 分)

---

## 评分结果

| 股票 | 代码 | 健康度 | 综合评分 | 价格趋势 | 动量 | 量价配合 | 估值位置 | 基本面 | PE_TTM | 涨跌幅 |
|------|------|--------|----------|----------|------|----------|----------|--------|--------|--------|
"""
    
    for priority in STOCKS.keys():
        priority_results = [r for r in results if r.get('优先级') == priority]
        if not priority_results:
            continue
        
        for r in priority_results:
            report += f"| {r['股票']} | {r['代码']} | {r['健康度']} | {r['综合评分']} | {r['价格趋势']} | {r['动量']} | {r['量价配合']} | {r['估值位置']} | {r['基本面']} | {r['PE_TTM'] or 'N/A'} | {r['涨跌幅(%)']}% |\n"
        report += "\n"
    
    # 统计摘要
    report += f"""---

## 统计摘要

| 等级 | 数量 | 占比 |
|------|------|------|
| 🟢 强势 | {len(strong)} 只 | {len(strong)/len(results)*100:.1f}% |
| 🟡 中性 | {len(neutral)} 只 | {len(neutral)/len(results)*100:.1f}% |
| 🔴 弱势 | {len(weak)} 只 | {len(weak)/len(results)*100:.1f}% |

**平均评分：** {sum(r['综合评分'] for r in results)/len(results):.1f}

---

## 重点关注

### 🟢 强势股（建议关注）

"""
    for r in sorted(strong, key=lambda x: x['综合评分'], reverse=True):
        report += f"- **{r['股票']}({r['代码']})**: 评分 {r['综合评分']}, PE={r['PE_TTM']}, 涨跌幅={r['涨跌幅(%)']}%\n"
    
    report += "\n### 🔴 弱势股（建议警惕）\n\n"
    for r in sorted(weak, key=lambda x: x['综合评分']):
        report += f"- **{r['股票']}({r['代码']})**: 评分 {r['综合评分']}, PE={r['PE_TTM']}, 涨跌幅={r['涨跌幅(%)']}%\n"
    
    report += f"\n*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
    
    return report


def main():
    """运行 GF-DMA 评分"""
    date_str = datetime.now().strftime("%Y%m%d")
    
    print("="*60)
    print("GF-DMA 健康度评分（混合版）")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # 加载数据
    print("\n加载数据...")
    pe_data = load_pe_data(date_str)
    price_data = load_price_data(date_str)
    finance_data = load_finance_data(date_str)
    
    print(f"  PE 数据: {len(pe_data)} 只")
    print(f"  实时价格: {len([p for p in price_data.values() if p and p.get('success')])} 只")
    print(f"  财务数据: {len(finance_data)} 只")
    
    # 评分
    print("\n开始评分...")
    results = []
    
    for priority, stock_list in STOCKS.items():
        print(f"\n【{priority}】")
        for name, code in stock_list:
            score = calculate_gfdma_score(code, price_data, pe_data, finance_data)
            score['优先级'] = priority
            score['股票'] = name
            results.append(score)
            print(f"  {name}({code}): {score['健康度']} ({score['综合评分']}分)")
    
    # 生成报告
    print("\n生成报告...")
    md_content = generate_report(results, date_str)
    md_path = OUTPUT_DIR / "gfdma" / f"GF-DMA_健康度评分_{date_str}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_content, encoding='utf-8')
    
    # 保存 CSV
    df = pd.DataFrame(results)
    csv_path = OUTPUT_DIR / "gfdma" / f"GF-DMA_健康度评分_{date_str}.csv"
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    # 统计
    strong = len([r for r in results if '🟢' in r['健康度']])
    neutral = len([r for r in results if '🟡' in r['健康度']])
    weak = len([r for r in results if '🔴' in r['健康度']])
    
    print(f"\n{'='*60}")
    print(f"✓ Markdown 报告: {md_path}")
    print(f"✓ CSV 数据: {csv_path}")
    print(f"🟢 强势: {strong} 只")
    print(f"🟡 中性: {neutral} 只")
    print(f"🔴 弱势: {weak} 只")
    print(f"{'='*60}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
