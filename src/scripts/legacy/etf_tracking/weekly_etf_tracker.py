#!/usr/bin/env python3
"""
每周ETF跟踪脚本 - 拉取462只ETF的实时行情 + 关键ETF的K线数据
执行频率：每周一
输出：更新到Obsidian vault + 生成简短报告
"""

import urllib.request
import json
import os
import re
from datetime import datetime

# === 配置 ===
ETFS_FILE = "/Users/xiashuang/.hermes/scripts/etf_tracking/etf_codes.txt"
OUTPUT_DIR = "/Users/xiashuang/obsidian/all about xia/01-股票投研/ETF/"
TENANT_API = "https://qt.gtimg.cn/q="
KLINE_API = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={code},day,,,120,qfq"

# 32只关键ETF（需要K线数据）
KEY_ETFS = [
    "sh515880", "sh588200", "sh513520", "sz159941", "sh513500",
    "sh562500", "sh515030", "sh512400", "sz159870", "sz159920",
    "sh512660", "sh512170", "sh512980", "sz159992", "sh512010",
    "sh589720", "sz159611", "sz159647", "sh513120", "sh588170",
    "sh512480", "sh510050", "sh510300", "sh588000", "sz159915",
    "sh512880", "sh515790", "sh512800", "sz159766", "sh513180",
    "sz159570", "sz159309"
]

def fetch_realtime(codes, batch_size=80):
    """批量获取实时行情"""
    results = {}
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        url = TENANT_API + ",".join(batch)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read().decode("gbk", errors="ignore")
            for line in data.strip().split("\n"):
                m = re.search(r'"(.+)"', line)
                if m:
                    fields = m.group(1).split("~")
                    if len(fields) > 40:
                        code = fields[2] if fields[2] else fields[0].replace("v_", "")
                        results[code] = {
                            "name": fields[1],
                            "price": fields[3],
                            "change_pct": fields[32],
                            "pe": fields[39]
                        }
        except Exception as e:
            print(f"Batch fetch error: {e}")
    return results

def compute_ma(prices, periods):
    """计算移动平均线"""
    if len(prices) < periods:
        return None
    return sum(prices[-periods:]) / periods

def main():
    # 1. 读取ETF代码列表
    etf_codes_tencent = []
    etf_codes_full = []
    with open(ETFS_FILE, "r") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) >= 3:
                etf_codes_tencent.append(parts[0])  # sh510770
                etf_codes_full.append(parts[1])      # 510770.SH

    # 2. 获取全部实时行情
    print(f"Fetching real-time data for {len(etf_codes_tencent)} ETFs...")
    realtime = fetch_realtime(etf_codes_tencent)
    print(f"Got {len(realtime)} results")

    # 3. 获取关键ETF的K线数据
    print("Fetching K-line data for key ETFs...")
    kline_results = {}
    for code in KEY_ETFS:
        url = KLINE_API.format(code=code)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
            # 解析数据
            stock_data = data.get("data", {}).get(code.replace("sh","").replace("sz",""), {})
            days = stock_data.get("day") or stock_data.get("qfqday", [])
            if days:
                closes = [float(d[2]) for d in days]  # 第2个字段是收盘价
                prices = [float(d[4]) for d in days]   # 第4个字段也是收盘价（不同格式）
                # 确定哪个字段是收盘价
                closes = []
                for d in days:
                    if len(d) >= 5:
                        closes.append(float(d[4]))  # day格式: date,open,high,low,close,volume
                if closes:
                    ma20 = compute_ma(closes, min(20, len(closes)))
                    ma60 = compute_ma(closes, min(60, len(closes)))
                    if ma20 and ma60:
                        kline_results[code] = {
                            "close": closes[-1],
                            "ma20": round(ma20, 4),
                            "ma60": round(ma60, 4),
                            "ma20_dev": round((closes[-1] - ma20) / ma20 * 100, 2),
                            "ma60_dev": round((closes[-1] - ma60) / ma60 * 100, 2),
                        }
        except Exception as e:
            print(f"K-line fetch error for {code}: {e}")

    # 4. 生成报告
    today = datetime.now().strftime("%Y-%m-%d")
    report = f"# ETF周度跟踪报告（{today}）\n\n"
    report += f"> 数据来源：腾讯财经实时API\n"
    report += f"> 更新：{today}\n\n"
    
    report += "## 一、关键ETF MA位置\n\n"
    report += "| ETF | 最新价 | MA20 | 对MA20% | MA60 | 对MA60% |\n"
    report += "|-----|--------|------|---------|------|--------|\n"
    for code in KEY_ETFS:
        full_code = code.replace("sh","").replace("sz","") + ".SH" if "sh" in code else code.replace("sz","") + ".SZ"
        k = kline_results.get(code, {})
        r = realtime.get(full_code, {})
        if k:
            report += f"| {full_code} | {k['close']} | {k['ma20']} | {k['ma20_dev']}% | {k['ma60']} | {k['ma60_dev']}% |\n"
    
    report += "\n## 二、MA20上方品种\n\n"
    above = [c for c, d in kline_results.items() if d['ma20_dev'] > 0]
    report += f"共{len(above)}只站上MA20：{', '.join(above)}\n\n"
    
    report += "## 三、MA20下方但差距<5%的品种\n\n"
    near = [(c, d['ma20_dev']) for c, d in kline_results.items() if -5 < d['ma20_dev'] < 0]
    near.sort(key=lambda x: x[1], reverse=True)
    for c, dev in near:
        report += f"- {c}: {dev}%\n"
    
    # 保存报告
    report_path = os.path.join(OUTPUT_DIR, f"ETF周度跟踪-{today}.md")
    with open(report_path, "w") as f:
        f.write(report)
    
    # 保存原始数据供对比
    data_path = os.path.join(OUTPUT_DIR, f"ETF周度数据-{today}.json")
    with open(data_path, "w") as f:
        json.dump({"realtime": realtime, "kline": {k: v for k, v in kline_results.items()}}, f, ensure_ascii=False)
    
    print(f"\nReport saved to: {report_path}")
    print(f"Data saved to: {data_path}")
    
    # 输出摘要
    print(f"\\n=== 周度摘要 ===")
    print(f"MA20上方: {len(above)}只")
    print(f"MA20下方<5%: {len(near)}只")
    if near:
        print(f"最接近MA20: {near[-1][0]} ({near[-1][1]}%)")
    # 追加：聚合摘要（增强输出内容量）
    innovative_etfs = [c for c in kline_results if any(kw in c.lower() for kw in ['588200','515880','515030','562500','588000'])]
    if innovative_etfs:
        avg_dev60 = sum(kline_results[c]['ma60_dev'] for c in innovative_etfs) / len(innovative_etfs)
        trend = "弱势空头" if avg_dev60 < 0 else "偏强"
        print(f"创新药ETF板块诊断: {trend} (MA60均偏离 {avg_dev60:.1f}%)")

    # 统计 MA20 上方/下方品种
    above_ma20_count = sum(1 for c, d in kline_results.items() if d.get('ma20_dev', 0) > 0)
    below_ma20_count = sum(1 for c, d in kline_results.items() if d.get('ma20_dev', 0) < -5)
    print(f"MA20上方: {above_ma20_count}只 | MA20下方>5%: {below_ma20_count}只")

    print(f"详细报告已保存: {report_path}")
    print(f"原始数据已保存: {data_path}")
    print(f"=== 完成 ===")
    
    # Silent 模式：无显著发现时输出 [SILENT]
    if not near and not above:
        print("[SILENT]")

if __name__ == "__main__":
    main()