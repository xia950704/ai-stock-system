#!/usr/bin/env python3
"""
板块轮动策略（趋势跟踪）
========================
配对套利在当前regime失效（价差趋势化不平稳），改用板块轮动——跟随已发生的动量，
不预测哪个强。哪个板块强就持有哪个，跌破均线或排名下滑就换仓。

核心逻辑（三条件）：
  1. 动量排名前N（ROC20+ROC60加权评分）
  2. 站上MA60（中期趋势确认，过滤下跌品种）
  3. ROC20>0（短期动量为正）

建仓：每周调仓，持有满足三条件的前3-5只ETF，等权分配
换仓：跌破MA60 或 跌出前N 或 ROC20转负 → 卖出，补入新进前N
空仓：无品种满足条件时持有货币基金（现金）

A股ETF做多版：无融券，趋势跟踪天然适合（只能做多=跟随上涨趋势）

用法:
  python3 strategies/rotation/engine.py                  # 跑回测
  python3 strategies/rotation/engine.py --signal         # 查当前信号
  python3 strategies/rotation/engine.py --report         # 生成报告→Obsidian
  python3 strategies/rotation/engine.py --hold 3         # 持有前3只
"""
import sys, os, json, urllib.request, argparse
from datetime import datetime
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VAULT_ETF_DIR = os.path.expanduser("~/obsidian/all about xia/01-股票投研/日更")

# ==================== 配置 ====================
INITIAL_CAPITAL = 50000.0
COMMISSION = 0.0005   # ETF佣金（万五，比股票低）
SLIPPAGE = 0.001
HOLD_TOP_N = 3        # 持有前N只
MA_PERIOD = 60        # 趋势确认均线
REBALANCE_DAYS = 10   # 调仓周期（v1=5太频繁震荡市反复打脸，v2=10降换手）
ROC_SHORT = 20        # 短期动量
ROC_LONG = 60         # 长期动量
ROC_WEIGHT = (1.0, 1.5)  # ROC20权重1.0，ROC60权重1.5（长期更重要）

# ==================== ETF标的池（20只跨板块） ====================
# 覆盖科技/AI/新能源/医药/消费/金融/周期，跨板块捕捉轮动
ETF_POOL = {
    '512400': '有色金属',
    '515880': '通信',
    '588200': '科创芯片',
    '515030': '新能源车',
    '515790': '光伏',
    '512480': '半导体',
    '515050': '5G通信',
    '588170': '科创芯片ETF',
    '512660': '军工',
    '561360': '石油',
    '518880': '黄金',
    '159941': '纳指100',
    '513500': '标普500',
    '512170': '医疗',
    '513120': '创新药',
    '512980': '传媒',
    '512200': '房地产',
    '159870': '化工',
    '512880': '证券',
    '512010': '医药',
}


def fetch_etf_close(code, count=1000):
    """腾讯接口取ETF日线收盘序列。count=1000约4年数据。返回(closes, dates)。"""
    market = 'sh' if code.startswith('5') else 'sz'
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={market}{code},day,,,{count},qfq"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=10).read().decode('utf-8'))
        d = data.get('data', {})
        if not d:
            return None, None
        key = list(d.keys())[0]
        arr = d[key].get('qfqday') or d[key].get('day') or []
        closes = [float(r[2]) for r in arr if len(r) > 2 and r[2]]
        dates = [r[0] for r in arr if len(r) > 2 and r[2]]
        if len(closes) > MA_PERIOD + 10:
            return np.array(closes), dates
        return None, None
    except Exception:
        return None, None


def fetch_all_etf_data():
    """批量拉取所有ETF收盘数据。"""
    data = {}
    for code, name in ETF_POOL.items():
        closes, dates = fetch_etf_close(code)
        if closes is not None:
            data[code] = {'name': name, 'closes': closes, 'dates': dates}
    return data


def compute_scores(closes_dict, idx):
    """计算某日的动量评分。返回 [(code, name, score, roc20, roc60, above_ma), ...] 按分数降序。"""
    scores = []
    for code, d in closes_dict.items():
        c = d['closes']
        if idx >= len(c) or idx < MA_PERIOD:
            continue
        price = c[idx]
        roc20 = (price - c[idx - ROC_SHORT]) / c[idx - ROC_SHORT] if idx >= ROC_SHORT and c[idx-ROC_SHORT] > 0 else 0
        roc60 = (price - c[idx - ROC_LONG]) / c[idx - ROC_LONG] if idx >= ROC_LONG and c[idx-ROC_LONG] > 0 else 0
        ma60 = np.mean(c[idx - MA_PERIOD:idx]) if idx >= MA_PERIOD else 0
        above_ma = price > ma60 if ma60 > 0 else False
        score = roc20 * ROC_WEIGHT[0] + roc60 * ROC_WEIGHT[1]
        scores.append({
            'code': code, 'name': d['name'], 'score': score,
            'roc20': roc20, 'roc60': roc60, 'above_ma': above_ma,
            'price': price,
        })
    # 降序
    scores.sort(key=lambda x: x['score'], reverse=True)
    return scores


def select_holdings(scores, top_n=HOLD_TOP_N):
    """四条件选股：排名前N + 站上MA60 + ROC20>0 + ROC60>0（双动量确认）。"""
    qualified = [s for s in scores if s['above_ma'] and s['roc20'] > 0 and s['roc60'] > 0]
    return qualified[:top_n]


def backtest():
    """轮动回测：逐日推进，每REBALANCE_DAYS调仓。"""
    print(f"\n{'='*60}")
    print(f"  📈 板块轮动策略回测")
    print(f"  初始资金: ¥{INITIAL_CAPITAL:,.0f} | 持有前{HOLD_TOP_N}只 | 调仓周期{REBALANCE_DAYS}天")
    print(f"  条件: 排名前N + 站上MA{MA_PERIOD} + ROC{ROC_SHORT}>0")
    print(f"{'='*60}")

    closes_dict = fetch_all_etf_data()
    # 过滤掉数据太短的ETF（要求≥2年，约480天，含牛熊周期）
    min_required = 480
    closes_dict = {c: d for c, d in closes_dict.items() if len(d['closes']) >= min_required}
    dropped = set(ETF_POOL.keys()) - set(closes_dict.keys())
    if dropped:
        print(f"  ⏭ 过滤数据不足的ETF(<{min_required}天): {[ETF_POOL[c] for c in dropped]}")
    print(f"  ✅ 获取 {len(closes_dict)}/{len(ETF_POOL)} 只ETF数据(≥{min_required}天)")

    if len(closes_dict) < 3:
        print("  ❌ 数据不足")
        return

    # 对齐长度（取所有ETF的最短长度）
    min_len = min(len(d['closes']) for d in closes_dict.values())
    # 日期参考序列（取第一个ETF的dates，按min_len截断尾部对齐）
    ref_code = list(closes_dict.keys())[0]
    ref_dates = closes_dict[ref_code]['dates'][-min_len:]
    print(f"  📅 回测区间: {ref_dates[0]} → {ref_dates[-1]} ({min_len}个交易日)")

    cash = INITIAL_CAPITAL
    holdings = {}  # {code: {shares, entry_price, entry_idx}}
    trades = []
    equity_curve = []
    last_rebalance = -REBALANCE_DAYS

    for idx in range(MA_PERIOD + ROC_LONG, min_len):
        # 调仓日
        if idx - last_rebalance >= REBALANCE_DAYS:
            last_rebalance = idx
            scores = compute_scores(closes_dict, idx)
            target = select_holdings(scores)
            target_codes = {s['code'] for s in target}

            # 卖出：不在目标池 或 跌出条件的
            to_sell = [c for c in holdings if c not in target_codes]
            for code in to_sell:
                price = closes_dict[code]['closes'][idx]
                revenue = holdings[code]['shares'] * price
                fee = revenue * (COMMISSION + SLIPPAGE)
                cash += revenue - fee
                ret = (price - holdings[code]['entry_price']) / holdings[code]['entry_price']
                trades.append({
                    'action': '卖出', 'code': code, 'name': closes_dict[code]['name'],
                    'entry': holdings[code]['entry_price'], 'exit': price,
                    'return': ret, 'idx': idx,
                    'reason': '跌出前N/跌破MA',
                })
                del holdings[code]

            # 买入：目标池里还没持有的
            slots = HOLD_TOP_N - len(holdings)
            if slots > 0 and cash > 1000:
                per_stock = cash / slots if slots > 0 else 0
                for s in target:
                    if s['code'] in holdings:
                        continue
                    code = s['code']
                    price = closes_dict[code]['closes'][idx]
                    cost = per_stock
                    shares = int(cost / price / 100) * 100  # ETF按100股整手
                    if shares <= 0:
                        continue
                    actual = shares * price
                    fee = actual * (COMMISSION + SLIPPAGE)
                    cash -= (actual + fee)
                    holdings[code] = {'shares': shares, 'entry_price': price, 'entry_idx': idx}
                    trades.append({
                        'action': '买入', 'code': code, 'name': s['name'],
                        'entry': price, 'exit': None, 'return': 0, 'idx': idx,
                        'reason': f"排名{(scores.index(s)+1)} ROC{s['roc20']:+.1%}",
                    })

        # 计算总权益
        total = cash
        for code, h in holdings.items():
            total += h['shares'] * closes_dict[code]['closes'][idx]
        # 日期（idx是全长度坐标，ref_dates从MA_PERIOD+ROC_LONG开始）
        date_str = ref_dates[idx - (MA_PERIOD + ROC_LONG)] if idx - (MA_PERIOD + ROC_LONG) < len(ref_dates) else ''
        equity_curve.append({'idx': idx, 'date': date_str, 'total': round(total, 2), 'holdings': len(holdings)})

    # 收盘清仓
    final_idx = min_len - 1
    for code in list(holdings.keys()):
        price = closes_dict[code]['closes'][final_idx]
        revenue = holdings[code]['shares'] * price
        fee = revenue * (COMMISSION + SLIPPAGE)
        cash += revenue - fee
        ret = (price - holdings[code]['entry_price']) / holdings[code]['entry_price']
        trades.append({'action': '收盘平仓', 'code': code, 'name': closes_dict[code]['name'],
                       'entry': holdings[code]['entry_price'], 'exit': price, 'return': ret, 'idx': final_idx})
        del holdings[code]

    # 绩效
    total_return = (cash - INITIAL_CAPITAL) / INITIAL_CAPITAL
    eq = pd.Series([e['total'] for e in equity_curve])
    if len(eq) > 1:
        rolling_max = eq.expanding().max()
        drawdown = (eq - rolling_max) / rolling_max
        max_dd = drawdown.min()
        daily_ret = eq.pct_change().dropna()
        sharpe = np.sqrt(252) * daily_ret.mean() / daily_ret.std() if daily_ret.std() > 0 else 0
    else:
        max_dd, sharpe = 0, 0

    buy_trades = [t for t in trades if t['action'] == '买入']
    sell_trades = [t for t in trades if t['action'] in ('卖出', '收盘平仓')]
    wins = sum(1 for t in sell_trades if t['return'] > 0)
    win_rate = wins / len(sell_trades) if sell_trades else 0

    print(f"\n  {'─'*50}")
    print(f"  💰 ¥{INITIAL_CAPITAL:,.0f} → ¥{cash:,.0f} ({total_return:+.2%})")
    print(f"  📊 买入{len(buy_trades)}次 | 卖出{len(sell_trades)}次 | 胜率{win_rate:.0%}")
    print(f"  🛡️ 夏普{sharpe:.2f} | 最大回撤{max_dd:.2%}")
    print(f"  📅 持仓天数{len(equity_curve)} | 平均持仓{np.mean([len([e for e in equity_curve if e['holdings']>0])/max(len(sell_trades),1)]):.0f}天")

    # 分年度绩效（v3新增，验证牛熊周期表现）
    if equity_curve and 'date' in equity_curve[0]:
        print(f"\n  📊 分年度绩效:")
        print(f"  {'年份':>6s} {'收益':>10s} {'持仓天数':>8s}")
        years = {}
        for e in equity_curve:
            y = e['date'][:4] if e['date'] else ''
            if y:
                years.setdefault(y, []).append(e)
        prev_total = INITIAL_CAPITAL
        for y in sorted(years.keys()):
            es = years[y]
            end_total = es[-1]['total']
            y_ret = (end_total - prev_total) / prev_total if prev_total > 0 else 0
            print(f"  {y:>6s} {y_ret:>+10.2%} {len(es):>8d}")
            prev_total = end_total

    if sell_trades:
        print(f"\n  最近交易:")
        for t in sell_trades[-8:]:
            print(f"    {t['action']} {t['name']}: {t['return']:+.2%} ({t['reason'] if 'reason' in t else ''})")

    # 对比基准：全仓持有第一只ETF
    first_code = list(closes_dict.keys())[0]
    first_closes = closes_dict[first_code]['closes']
    bm_return = (first_closes[final_idx] - first_closes[MA_PERIOD+ROC_LONG]) / first_closes[MA_PERIOD+ROC_LONG]
    print(f"\n  📊 对比基准(全仓{closes_dict[first_code]['name']}): {bm_return:+.2%}")

    return {'total_return': total_return, 'sharpe': sharpe, 'max_dd': max_dd,
            'win_rate': win_rate, 'n_trades': len(sell_trades),
            'final_capital': cash, 'equity_curve': equity_curve, 'trades': trades}


def check_signal():
    """查当前轮动信号。"""
    print(f"\n{'='*60}")
    print(f"  📊 板块轮动当前信号 - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    closes_dict = fetch_all_etf_data()
    idx = max(len(d['closes']) - 1 for d in closes_dict.values())
    scores = compute_scores(closes_dict, idx)
    target = select_holdings(scores)

    print(f"\n  完整排名 (共{len(scores)}只):")
    print(f"  {'排名':>4s} {'品种':<10s} {'评分':>8s} {'ROC20':>8s} {'ROC60':>8s} {'MA60':>6s} {'状态':>6s}")
    print(f"  {'-'*56}")
    for i, s in enumerate(scores, 1):
        ma_str = "上方✅" if s['above_ma'] else "下方❌"
        status = "🟢持有" if s in target else "⚪观望"
        print(f"  {i:>4d} {s['name']:<10s} {s['score']:>+8.3f} {s['roc20']:>+8.1%} {s['roc60']:>+8.1%} {ma_str:>6s} {status:>6s}")

    print(f"\n  🎯 建仓建议: 持有前{HOLD_TOP_N}只（站上MA{MA_PERIOD}+ROC{ROC_SHORT}>0）")
    if target:
        print(f"  推荐持有: {', '.join(s['name'] for s in target)}")
    else:
        print(f"  ⚪ 无品种满足条件，空仓持有货币基金")
    return target


def generate_report():
    """生成轮动信号日报→Obsidian。"""
    target = check_signal()
    today = datetime.now().strftime('%Y-%m-%d')

    lines = []
    lines.append(f"# 📊 板块轮动信号日报 {today}")
    lines.append("")
    lines.append(f"> 策略: 动量轮动 | 条件: 排名前{HOLD_TOP_N}+站上MA{MA_PERIOD}+ROC{ROC_SHORT}>0")
    lines.append(f"> 调仓周期: 每{REBALANCE_DAYS}天 | 资金: ¥{INITIAL_CAPITAL:,.0f}")
    lines.append("")
    lines.append("## 🎯 建仓建议")
    lines.append("")
    if target:
        lines.append("| 品种 | 评分 | ROC20 | ROC60 | 仓位 |")
        lines.append("|------|------|-------|-------|------|")
        weight = 1.0 / len(target)
        for s in target:
            lines.append(f"| {s['name']}({s['code']}) | {s['score']:+.3f} | {s['roc20']:+.1%} | {s['roc60']:+.1%} | {weight:.0%} |")
    else:
        lines.append("⚪ 无品种满足三条件，空仓持有货币基金")
    lines.append("")
    lines.append("> ⚠️ 趋势跟踪策略：跌破MA60或跌出前N即换仓，不扛跌")
    lines.append(f"*报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    content = "\n".join(lines)
    out_path = os.path.join(VAULT_ETF_DIR, f"轮动信号_{today}.md")
    os.makedirs(VAULT_ETF_DIR, exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"\n  ✅ 报告写入: {out_path}")


def main():
    global HOLD_TOP_N
    parser = argparse.ArgumentParser(description='板块轮动策略')
    parser.add_argument('--signal', action='store_true', help='查当前信号')
    parser.add_argument('--report', action='store_true', help='生成报告→Obsidian')
    parser.add_argument('--hold', type=int, default=HOLD_TOP_N, help=f'持有前N只(默认{HOLD_TOP_N})')
    args = parser.parse_args()

    HOLD_TOP_N = args.hold

    if args.signal:
        check_signal()
    elif args.report:
        generate_report()
    else:
        backtest()


if __name__ == '__main__':
    main()
