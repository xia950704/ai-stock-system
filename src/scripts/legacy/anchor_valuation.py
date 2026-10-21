#!/usr/bin/python3
"""
P0 锚价估值推断脚本（2026-08-26 新建）
====================================
给 price_alert.py v2 的手工锚价补"推断依据"。

问题：price_alert.py 的 BUY_PRICES 是拍脑袋定的（华东28、恒瑞50...），
      01-股票分析框架.md 第八章写了四维交叉验证（价格/事件/管线/估值），
      但锚价生成时估值维度从没用上。本脚本补这一环。

方法：PE历史分位法（主）+ PS法（亏损企业备用）
  推断公允价 = EPS(TTM) × PE历史分位值
  - PE 10%分位 = 极端低估区 → 推断建仓价（保守）
  - PE 20%分位 = 低估区 → 推断加仓价
  - PE 50%分位 = 中枢 → 推断合理价
  亏损企业（PE<0）：改用 PS分位法，推断公允价 = 每股营收 × PS分位值

输出：写入 vault 的 data/anchor_valuation_<date>.md，并与手工锚对比
"""
import os
import json
import urllib.request
from datetime import datetime
from pathlib import Path

VAULT_PATH = Path(os.path.expanduser("~/obsidian/all about xia"))
OUT_DIR = VAULT_PATH / "01-股票投研" / "data"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 手工锚（来自 price_alert.py v2，对应投资笔记）
MANUAL_ANCHORS = {
    '600276': {'name': '恒瑞医药', 'manual_buy': 50, 'note': '创新药龙头，回踩50-51'},
    '000963': {'name': '华东医药', 'manual_buy': 28, 'note': '医美+仿制药，28以下第一批'},
    '600079': {'name': '人福医药', 'manual_buy': 16.5, 'note': 'ST修复，仓位减半'},
    '002422': {'name': '科伦药业', 'manual_buy': 43, 'note': 'SKB264受理，回踩43-44'},
    '603259': {'name': '药明康德', 'manual_buy': 142, 'note': '中报超预期，回踩142-145'},
    '688506': {'name': '百利天恒', 'manual_buy': 285, 'note': '科创板流动性折价'},
    '002262': {'name': '恩华药业', 'manual_buy': 21, 'note': '中报后20-21企稳'},
}


def fetch_valuation(code):
    """东方财富估值数据（PE/PB/PS/市值/股本，约8年历史）。"""
    import akshare as ak
    try:
        df = ak.stock_value_em(symbol=code)
        return df
    except Exception as e:
        print(f"  ❌ {code} 估值获取失败: {e}")
        return None


def infer_anchor_pe(df):
    """PE历史分位法推断公允价。
    返回: {eps, pe_now, pe_p10, pe_p20, pe_p50, price_p10, price_p20, price_p50, current_price}
    price_p10 = EPS × PE历史10%分位（保守建仓价）
    """
    df = df.dropna(subset=['PE(TTM)', '当日收盘价']).copy()
    df = df[df['PE(TTM)'] > 0]  # 排除亏损期
    if len(df) < 30:
        return None

    latest = df.iloc[-1]
    current_price = float(latest['当日收盘价'])
    pe_now = float(latest['PE(TTM)'])
    # EPS = 价格 / PE
    eps = current_price / pe_now if pe_now > 0 else None
    if eps is None or eps <= 0:
        return None

    pe_p10 = float(df['PE(TTM)'].quantile(0.10))
    pe_p20 = float(df['PE(TTM)'].quantile(0.20))
    pe_p50 = float(df['PE(TTM)'].quantile(0.50))

    return {
        'method': 'PE分位法',
        'eps': round(eps, 3),
        'pe_now': round(pe_now, 2),
        'pe_p10': round(pe_p10, 2),
        'pe_p20': round(pe_p20, 2),
        'pe_p50': round(pe_p50, 2),
        'price_p10': round(eps * pe_p10, 2),  # 极端低估→建仓价
        'price_p20': round(eps * pe_p20, 2),  # 低估→加仓价
        'price_p50': round(eps * pe_p50, 2),  # 中枢→合理价
        'current_price': round(current_price, 2),
        'data_days': len(df),
    }


def infer_anchor_ps(df):
    """PS历史分位法（亏损企业备用）。
    推断公允价 = 每股营收 × PS分位值
    """
    df = df.dropna(subset=['市销率', '当日收盘价', '总市值', '总股本']).copy()
    if len(df) < 30:
        return None
    latest = df.iloc[-1]
    current_price = float(latest['当日收盘价'])
    total_share = float(latest['总股本'])
    mkt_cap = float(latest['总市值'])  # 单位已是元
    # 每股营收 = 总市值 / PS / 总股本
    ps_now = float(latest['市销率'])
    if ps_now <= 0 or total_share <= 0:
        return None
    revenue_per_share = (mkt_cap / ps_now) / total_share

    # 只用PS>0的数据算分位
    ps_valid = df[df['市销率'] > 0]['市销率']
    if len(ps_valid) < 30:
        return None
    ps_p10 = float(ps_valid.quantile(0.10))
    ps_p20 = float(ps_valid.quantile(0.20))
    ps_p50 = float(ps_valid.quantile(0.50))

    return {
        'method': 'PS分位法',
        'rev_per_share': round(revenue_per_share, 3),
        'ps_now': round(ps_now, 2),
        'ps_p10': round(ps_p10, 2),
        'ps_p20': round(ps_p20, 2),
        'ps_p50': round(ps_p50, 2),
        'price_p10': round(revenue_per_share * ps_p10, 2),
        'price_p20': round(revenue_per_share * ps_p20, 2),
        'price_p50': round(revenue_per_share * ps_p50, 2),
        'current_price': round(current_price, 2),
        'data_days': len(df),
    }


def infer_anchor(code, name):
    """对单只股票推断锚价。优先PE法，亏损转PS法。"""
    df = fetch_valuation(code)
    if df is None:
        return None

    latest_pe = df.iloc[-1].get('PE(TTM)', 0)
    if pd_is_positive(latest_pe):
        result = infer_anchor_pe(df)
        if result:
            return result
    # PE失效或为负 → PS法
    result = infer_anchor_ps(df)
    if result:
        return result
    return {'method': '失败', 'error': 'PE/PS均无法推断'}


def pd_is_positive(v):
    try:
        return float(v) > 0
    except Exception:
        return False


def generate_report(results):
    """生成锚价推断报告。"""
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%H:%M")

    lines = []
    lines.append(f"# 📐 P0 锚价估值推断 — {today}")
    lines.append("")
    lines.append(f"**生成时间**: {now}")
    lines.append("")
    lines.append("> 方法: PE历史分位法(主) / PS分位法(亏损企业)")
    lines.append("> price_p10=极端低估建仓价, price_p20=低估加仓价, price_p50=中枢合理价")
    lines.append("> 数据源: 东方财富估值(约8年历史)")
    lines.append("")
    lines.append("## 锚价对比（手工锚 vs 推断锚）")
    lines.append("")
    lines.append("| 名称 | 代码 | 方法 | 现价 | 当前PE | 推断建仓价(p10) | 推断加仓价(p20) | 中枢价(p50) | 手工锚 | 锚差 | 判定 |")
    lines.append("|------|------|------|------|--------|----------------|----------------|------------|--------|------|------|")

    for code, r in results.items():
        info = MANUAL_ANCHORS[code]
        if not r or r.get('method') == '失败':
            lines.append(f"| {info['name']} | {code} | 失败 | - | - | - | - | - | {info['manual_buy']} | - | ❌ |")
            continue

        manual = info['manual_buy']
        p10 = r['price_p10']
        diff_pct = (manual - p10) / p10 * 100 if p10 > 0 else 0
        # 判定：手工锚在 p10±15% 内=合理；低于p10=偏保守；高于p20=偏激进
        if p10 > 0:
            if abs(diff_pct) <= 15:
                verdict = "✅ 合理"
            elif diff_pct < -15:
                verdict = "🟡 偏保守(锚低于推断)"
            elif manual > r.get('price_p20', 0):
                verdict = "🔴 偏激进(锚高于加仓价)"
            else:
                verdict = "🟡 偏保守"
        else:
            verdict = "⚠️ 推断失效"

        pe_now = r.get('pe_now', r.get('ps_now', '-'))
        lines.append(
            f"| {info['name']} | {code} | {r['method']} | {r['current_price']} | {pe_now} | "
            f"**{p10}** | {r.get('price_p20', '-')} | {r.get('price_p50', '-')} | "
            f"{manual} | {diff_pct:+.0f}% | {verdict} |"
        )

    lines.append("")
    lines.append("## 推断明细")
    lines.append("")
    for code, r in results.items():
        info = MANUAL_ANCHORS[code]
        if not r or r.get('method') == '失败':
            lines.append(f"### {info['name']}({code}) — 推断失败")
            lines.append("")
            continue
        lines.append(f"### {info['name']}({code}) — {r['method']}")
        lines.append("")
        if r['method'] == 'PE分位法':
            lines.append(f"- EPS(TTM): ¥{r['eps']}（现价/当前PE反推）")
            lines.append(f"- 当前PE: {r['pe_now']} | 历史10%分位: {r['pe_p10']} | 20%: {r['pe_p20']} | 50%: {r['pe_p50']}")
            lines.append(f"- 推断建仓价(p10): **¥{r['price_p10']}** = EPS × PE历史10%分位")
            lines.append(f"- 推断加仓价(p20): ¥{r['price_p20']}")
            lines.append(f"- 中枢合理价(p50): ¥{r['price_p50']}")
        else:
            lines.append(f"- 每股营收: ¥{r['rev_per_share']}（PS法，PE为负）")
            lines.append(f"- 当前PS: {r['ps_now']} | 历史10%分位: {r['ps_p10']} | 20%: {r['ps_p20']} | 50%: {r['ps_p50']}")
            lines.append(f"- 推断建仓价(p10): **¥{r['price_p10']}**")
            lines.append(f"- 推断加仓价(p20): ¥{r['price_p20']}")
            lines.append(f"- 中枢合理价(p50): ¥{r['price_p50']}")
        lines.append(f"- 数据样本: {r['data_days']}天")
        lines.append(f"- 手工锚: ¥{info['manual_buy']}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## 应用建议")
    lines.append("")
    lines.append("1. price_alert.py v2 的 BUY_PRICES 可用推断p10价替换手工锚（有依据）")
    lines.append("2. 锚差>±15%的股票需复盘：手工锚是否需更新")
    lines.append("3. 亏损企业(百利天恒)用PS法，PE法不适用")
    lines.append(f"*报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")
    return "\n".join(lines)


def main():
    print("=" * 50)
    print("📐 P0 锚价估值推断")
    print(f"   日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    results = {}
    for code, info in MANUAL_ANCHORS.items():
        print(f"\n  ▶ {info['name']}({code})...")
        r = infer_anchor(code, info['name'])
        results[code] = r
        if r and r.get('method') != '失败':
            print(f"    {r['method']}: 推断建仓价 ¥{r.get('price_p10', '?')} (现价 ¥{r.get('current_price', '?')}, 手工锚 ¥{info['manual_buy']})")
        else:
            print(f"    ❌ 推断失败")

    report = generate_report(results)
    date_str = datetime.now().strftime("%Y%m%d")
    out_path = OUT_DIR / f"anchor_valuation_{date_str}.md"
    out_path.write_text(report)
    print(f"\n  ✅ 报告写入: {out_path}")


if __name__ == '__main__':
    main()
