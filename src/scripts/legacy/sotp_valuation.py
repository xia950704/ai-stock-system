#!/usr/bin/python3
"""
SOTP 管线估值法（2026-08-27 新建）
================================
PE/PS历史分位法对创新药失效（估值中枢移动），改用 SOTP（Sum-Of-The-Parts）。
把公司拆成几块业务分别估值再加总，得到公允价。

适用：科伦药业（大输液+ADC+中间体）、百利天恒（单一管线ADC）、药明康德（CRDMO平台）

方法论：
  1. 现有业务（已上市/稳定现金流）→ PE法或DCFF
  2. 在研管线（NDA已提交/III期）→ 风险调整NPV（rNPV）
     rNPV = 峰值销售额 × 净利率 × 估值倍数 × 获批概率 × 折现
  3. BD授权（已签约里程碑）→ 按概率加总里程碑金额
  4. 现金净额（账面）→ 直接加
  5. 总市值 = 1+2+3+4，每股 = 总市值/总股本

关键假设需手工标注（基于行业经验，非精确预测）：
  - 峰值销售额（对标同类药）
  - 获批概率（临床阶段对应历史成功率）
  - 估值倍数（PS峰值，创新药6-10x）

用法:
  python3 sotp_valuation.py           # 计算并生成报告
  python3 sotp_valuation.py --preview  # 只预览
"""
import os, json
from datetime import datetime
from pathlib import Path

VAULT = Path(os.path.expanduser("~/obsidian/all about xia/01-股票投研/data"))

# ==================== 三只股票的 SOTP 拆分假设 ====================
# 所有假设基于投资笔记+行业经验，标注依据。非精确预测，是合理区间。
# 单位：亿元（人民币）

DISCOUNT_RATE = 0.10  # 折现率10%（创新药风险溢价）

STOCKS = {
    '002422': {
        'name': '科伦药业',
        'current_price': 43.64,
        'total_share': 14.24,  # 亿股
        'parts': {
            # 1. 现有业务：大输液+抗生素中间体（成熟业务，PE法）
            '现有业务': {
                'method': 'PE法',
                'net_profit_2025': 25,  # 2025扣非净利约25亿（投资笔记数据）
                'pe_fair': 12,  # 传统药企合理PE 10-15x，给12x
                'value': 25 * 12,  # 300亿
                'note': '大输液+中间体，成熟现金流，PE 12x'
            },
            # 2. SKB264（TROP2 ADC，NDA已受理，对标Trodelvy）
            'SKB264': {
                'method': 'rNPV',
                'peak_sales': 80,  # 峰值销售80亿（对标Enhertu/Trodelvy中国市场）
                'profit_margin': 0.30,  # ADC净利率30%（高毛利）
                'ps_multiple': 6,  # 创新药峰值PS 6x
                'approval_prob': 0.85,  # NDA已受理，获批概率85%
                'years_to_peak': 5,  # 5年达峰
                'note': 'TROP2 ADC，NDA受理，对标Trodelvy'
            },
            # 3. 默沙东BD授权（90亿美元，7款管线，里程碑按概率）
            '默沙东BD': {
                'method': '里程碑加总',
                'total_deal': 90 * 7.2,  # 90亿美元≈648亿人民币
                'realized_pct': 0.15,  # 已实现首付部分15%
                'future_prob': 0.35,  # 后续里程碑综合达成概率35%
                'note': '90亿美元7款ADC，首付+里程碑'
            },
            # 4. 其他在研管线（A166等，粗估）
            '其他管线': {
                'method': 'rNPV',
                'peak_sales': 20,
                'profit_margin': 0.30,
                'ps_multiple': 5,
                'approval_prob': 0.40,  # 早期阶段概率低
                'years_to_peak': 6,
                'note': 'A166等早期管线，概率折价'
            },
        }
    },
    '688506': {
        'name': '百利天恒',
        'current_price': 269.18,
        'total_share': 4.13,  # 亿股
        'parts': {
            # 1. BL-B01D1 国内（EGFR×HER3双抗ADC，NDA已提交，中国市场销售分成）
            'BL-B01D1国内': {
                'method': 'rNPV',
                'peak_sales': 60,  # 峰值60亿（EGFR突变肺癌大适应症）
                'profit_margin': 0.35,
                'ps_multiple': 7,
                'approval_prob': 0.80,  # NDA已提交
                'years_to_peak': 5,
                'note': '国内销售，NDA已提交，对标Enhertu'
            },
            # 2. BL-B01D1 海外峰值分成（BMS商业化，百利按分成率15%计海外峰值）
            'BL-B01D1海外分成': {
                'method': 'rNPV',
                'peak_sales': 30,  # 全球峰值200亿×15%分成率=30亿（百利口径）
                'profit_margin': 0.80,  # 分成收入净利率高（无生产成本）
                'ps_multiple': 6,
                'approval_prob': 0.65,  # 海外FDA获批概率65%（III期阶段）
                'years_to_peak': 6,
                'note': 'BMS海外商业化，百利15%销售分成'
            },
            # 3. BMS BD（84亿美元，首付+里程碑）
            'BMS_BD': {
                'method': '里程碑加总',
                'total_deal': 84 * 7.2,  # 84亿美元≈605亿
                'realized_pct': 0.13,  # 首付约8亿/84亿=10%+小里程碑
                'future_prob': 0.30,
                'note': 'BMS 84亿美元，首付+里程碑'
            },
            # 4. 其他管线（BL-M001等，早期）
            '其他管线': {
                'method': 'rNPV',
                'peak_sales': 25,
                'profit_margin': 0.30,
                'ps_multiple': 5,
                'approval_prob': 0.25,
                'years_to_peak': 7,
                'note': 'BL-M001等早期，概率低'
            },
            # 5. 现金（账面，2025中报数据估算）
            '现金净额': {
                'method': '直接',
                'value': 15,  # 账面现金15亿
                'note': '账面现金（估算）'
            },
        }
    },
    '603259': {
        'name': '药明康德',
        'current_price': 159.25,
        'total_share': 29.06,  # 亿股
        'parts': {
            # 药明是CRDMO平台，非管线型，按业务板块估值
            # 1. 化学业务（WuXi Chemistry，核心现金流）
            '化学业务CRDMO': {
                'method': 'PE法',
                'net_profit_2025': 100,  # 2025净利约100亿（中报已验证）
                'pe_fair': 18,  # CXO合理PE 15-20x
                'value': 100 * 18,
                'note': '化学CRDMO核心，PE 18x'
            },
            # 2. 测试业务（已出售CGT/临床，聚焦）
            '测试业务': {
                'method': 'PE法',
                'net_profit_2025': 15,
                'pe_fair': 15,
                'value': 15 * 15,
                'note': '实验室测试，PE 15x'
            },
            # 3. TIDES（多肽/寡核苷酸，高增长）
            'TIDES业务': {
                'method': 'PE法',
                'net_profit_2025': 20,
                'pe_fair': 25,  # 高增长给溢价
                'value': 20 * 25,
                'note': '多肽高增长，PE 25x'
            },
            # 4. 地缘风险折价
            '地缘风险折价': {
                'method': '折价',
                'discount_pct': 0.15,  # 美国生物安全法案风险折价15%
                'note': '生物安全法案不确定性折价'
            },
        }
    },
}


def calc_rnpv(part):
    """计算风险调整NPV。"""
    peak = part['peak_sales']
    margin = part['profit_margin']
    ps = part['ps_multiple']
    prob = part['approval_prob']
    years = part['years_to_peak']
    # 峰值估值 = 峰值销售 × 净利率 × PS倍数
    peak_value = peak * margin * ps
    # 折现到当前（简单折现，假设线性增长达峰后维持）
    discount = 1 / (1 + DISCOUNT_RATE) ** years
    # 风险调整
    rnpv = peak_value * prob * discount
    return rnpv, peak_value


def calc_milestone(part):
    """计算BD里程碑价值。"""
    total = part['total_deal']
    realized = total * part['realized_pct']  # 已到手部分
    future = total * (1 - part['realized_pct']) * part['future_prob']  # 未来里程碑按概率
    return realized + future


def calc_sotp(stock):
    """计算单只股票SOTP。"""
    parts_val = {}
    total = 0
    for pname, p in stock['parts'].items():
        if p['method'] == 'PE法':
            v = p['value']
        elif p['method'] == 'rNPV':
            v, peak = calc_rnpv(p)
            p['_peak_value'] = peak
        elif p['method'] == '里程碑加总':
            v = calc_milestone(p)
            p['_realized'] = p['total_deal'] * p['realized_pct']
            p['_future'] = p['total_deal'] * (1 - p['realized_pct']) * p['future_prob']
        elif p['method'] == '直接':
            v = p['value']
        elif p['method'] == '折价':
            # 折价在最后从总市值扣
            v = 0
            p['_is_discount'] = True
        parts_val[pname] = v
        if not p.get('_is_discount'):
            total += v

    # 应用折价
    for p in stock['parts'].values():
        if p.get('_is_discount'):
            total = total * (1 - p['discount_pct'])

    per_share = total / stock['total_share']
    current_mkt = stock['current_price'] * stock['total_share']
    upside = (per_share - stock['current_price']) / stock['current_price'] * 100

    return {
        'parts_val': parts_val,
        'total_value': total,
        'per_share': per_share,
        'current_mkt': current_mkt,
        'upside_pct': upside,
    }


def generate_report(results):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = []
    lines.append(f"# 📐 SOTP 管线估值报告 — {today}")
    lines.append("")
    lines.append(f"> 方法: 分部加总(Sum-Of-The-Parts)")
    lines.append(f"> 适用: 创新药管线估值(PE/PS历史分位法失效)")
    lines.append(f"> 折现率: {DISCOUNT_RATE:.0%} | 获批概率按临床阶段历史成功率")
    lines.append("")

    for code, r in results.items():
        s = STOCKS[code]
        lines.append(f"## {s['name']}({code})")
        lines.append("")
        lines.append(f"**SOTP公允价: ¥{r['per_share']:.2f}** | 现价: ¥{s['current_price']} | "
                     f"{'低估' if r['upside_pct']>0 else '高估'} {abs(r['upside_pct']):.0f}%")
        lines.append("")
        lines.append(f"| 业务分部 | 估值方法 | 估值(亿) | 占比 | 说明 |")
        lines.append(f"|---------|---------|---------|------|------|")
        for pname, v in r['parts_val'].items():
            p = s['parts'][pname]
            pct = v / r['total_value'] * 100 if r['total_value'] > 0 else 0
            lines.append(f"| {pname} | {p['method']} | {v:.0f} | {pct:.0f}% | {p['note']} |")
        lines.append(f"| **合计** | | **{r['total_value']:.0f}** | 100% | |")
        lines.append(f"")
        lines.append(f"- 每股公允价: ¥{r['per_share']:.2f}（总市值{r['total_value']:.0f}亿 / 股本{s['total_share']}亿股）")
        lines.append(f"- 现价对应市值: {r['current_mkt']:.0f}亿")
        lines.append(f"- {'🟢 低估' if r['upside_pct']>0 else '🔴 高估'} {abs(r['upside_pct']):.0f}%")
        lines.append("")

    lines.append("## 假设依据")
    lines.append("")
    lines.append("**获批概率（临床阶段历史成功率，BIO数据）:**")
    lines.append("- NDA已受理/提交: 85-90%（科伦SKB264/百利BL-B01D1）")
    lines.append("- III期: 60%（其他在研）")
    lines.append("- II期: 30%（早期管线）")
    lines.append("")
    lines.append("**峰值销售对标:**")
    lines.append("- SKB264对标Trodelvy（TROP2 ADC），中国市场峰值80亿")
    lines.append("- BL-B01D1对标Enhertu（HER2 ADC），EGFR肺癌大适应症峰值60亿")
    lines.append("- PS倍数: 成熟创新药6-8x，早期5x")
    lines.append("")
    lines.append("**BD里程碑:**")
    lines.append("- 科伦-默沙东90亿美元7款ADC，综合达成率35%")
    lines.append("- 百利-BMS 84亿美元BL-B01D1，综合达成率30%")
    lines.append("")
    lines.append("**药明康德特殊性:** 非管线型，CRDMO平台按业务板块PE法，加地缘风险折价15%")
    lines.append("")
    lines.append("## 局限")
    lines.append("- 峰值销售是预测值，实际可能±50%")
    lines.append("- 获批概率是行业平均，个股差异大")
    lines.append("- BD里程碑达成率是主观估计，可能高估")
    lines.append("- 不含竞争管线追赶（同类ADC上市后份额被瓜分）")
    lines.append(f"*报告时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)


def main():
    results = {}
    for code, s in STOCKS.items():
        r = calc_sotp(s)
        results[code] = r
        print(f"  {s['name']}({code}): SOTP公允价 ¥{r['per_share']:.2f} "
              f"(现价¥{s['current_price']}, {'低估' if r['upside_pct']>0 else '高估'}{abs(r['upside_pct']):.0f}%)")

    report = generate_report(results)
    out = VAULT / f"sotp_valuation_{datetime.now().strftime('%Y%m%d')}.md"
    out.write_text(report)
    print(f"\n  ✅ 报告写入: {out}")


if __name__ == '__main__':
    main()
