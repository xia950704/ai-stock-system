#!/usr/bin/env python3
"""
每日行情更新脚本（A股收盘后15:30执行）
- 扫描 vault 中所有股票估值追踪文件（含 #估值追踪 标签）
- 批量拉取腾讯 API 行情数据
- 更新所有估值追踪笔记
- 输出核心摘要
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

# ===== Config =====
VAULT = "/Users/xiashuang/obsidian/all about xia"
TRACKING_DIR = os.path.join(VAULT, "01-股票投研", "股票")
TODAY = date.today().isoformat()  # 2026-06-22

# Stock code patterns - 6 digits for A-shares, 5 digits for HK
STOCK_CODE_RE = re.compile(r'(\d{5,6})\.(SH|SZ|HK|BJ)')

# Tencent API
TENCENT_API = "https://qt.gtimg.cn/q={}"

# Core 5 stocks for special annotation
CORE_STOCKS = {"恒瑞医药", "华东医药", "人福医药", "科伦药业", "药明康德"}

# HK stocks have suffix
HK_MARKET = {"02162", "09926", "01801", "01177", "01093", "02005", "00332", "00853", "01066", "00241", "00348", "01302", "06990", "02269", "00570"}
BJ_MARKET = {"920566", "832566"}

# ==== Step 1: Scan valuation tracking files ====
def scan_valuation_files():
    """Scan all files with #估值追踪 tag in 01-股票投研/"""
    files = []
    
    # Also scan for files with 估值追踪 in the filename
    for root, dirs, filenames in os.walk(TRACKING_DIR):
        for fn in filenames:
            if "估值追踪" in fn and fn.endswith(".md"):
                fpath = os.path.join(root, fn)
                files.append(fpath)
    
    # Deduplicate - prefer shorter filenames (stock-name over stock-code-name)
    # Group by stock directory
    stock_groups = {}
    for fpath in files:
        parent = os.path.dirname(fpath)
        dirname = os.path.basename(parent)
        if dirname not in stock_groups:
            stock_groups[dirname] = []
        stock_groups[dirname].append(fpath)
    
    # For each stock, prefer the simpler filename (e.g., 恒瑞医药-估值追踪.md over 恒瑞医药(600276.SH)估值追踪.md)
    selected = []
    for dirname, fpaths in stock_groups.items():
        # Prefer the one without stock code in name
        simple = [f for f in fpaths if not re.search(r'\d{6}', os.path.basename(f))]
        if simple:
            selected.append(simple[0])
        else:
            selected.append(fpaths[0])
    
    return sorted(selected)

def extract_stock_code(filepath, stock_dir_name):
    """Extract stock code from file content or filename."""
    dirpath = os.path.dirname(filepath)
    filename = os.path.basename(filepath)

    # First check the selected file's own filename
    m = STOCK_CODE_RE.search(filename)
    if m:
        return m.group(1), m.group(2)

    # Check the file content
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Look for title with stock code
    m = re.search(r'#\s+.*?(\d{5,6})\.(SH|SZ|HK|BJ)', content)
    if m:
        return m.group(1), m.group(2)

    # Look for code in first 30 lines
    m = re.search(r'(\d{5,6})\.(SH|SZ|HK|BJ)', content[:3000])
    if m:
        return m.group(1), m.group(2)

    # Fallback: check other files in directory
    for fn in sorted(os.listdir(dirpath)):
        if fn == filename:
            continue
        if fn.endswith(".md"):
            m = STOCK_CODE_RE.search(fn)
            if m:
                return m.group(1), m.group(2)

    return None, None


# ===== Step 2: Fetch Tencent API =====
def fetch_tencent_quotes(codes_with_markets):
    """
    Fetch from Tencent stock API.
    Format: https://qt.gtimg.cn/q=sh600079,sz000963,s_hk02162
    """
    if not codes_with_markets:
        return {}
    
    # Build query string
    query_parts = []
    for code, market in codes_with_markets:
        if market == 'SH':
            query_parts.append(f"sh{code}")
        elif market == 'SZ':
            query_parts.append(f"sz{code}")
        elif market == 'HK':
            query_parts.append(f"hk{code}")
        elif market == 'BJ':
            query_parts.append(f"bj{code}")
    
    # Remove duplicates
    query_parts = list(set(query_parts))
    
    # Split into batches of 20 to avoid too-long URLs
    batch_size = 20
    all_results = {}
    
    for i in range(0, len(query_parts), batch_size):
        batch = query_parts[i:i+batch_size]
        query = ",".join(batch)
        url = f"https://qt.gtimg.cn/q={query}"
        
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read().decode('gbk')
                
            for line in data.strip().split('\n'):
                if not line.strip():
                    continue
                # Parse: v_sz000963="...~name~code~price~...";
                m = re.search(r'v_([a-z]+)(\d+)="(.+)"', line)
                if not m:
                    continue
                prefix = m.group(1)
                code_num = m.group(2)
                fields = m.group(3).split('~')
                
                # Tencent format fields (verified live):
                # 0: market(1=shenzhen), 1: name, 2: code, 3: current_price
                # 4: yesterday_close, 5: open, 6: volume(lots), 7-8: bid/ask
                # 9: high, 32: change%, 34: low, 37: turnover_amount(万元)
                # 38: turnover_rate(%), 39: PE(TTM) ✓, 43: amplitude(%)
                if len(fields) > 5:
                    result = {
                        'name': fields[1] if len(fields) > 1 else '',
                        'code': fields[2] if len(fields) > 2 else code_num,
                        'price': fields[3] if len(fields) > 3 and fields[3] else '0.00',
                        'prev_close': fields[4] if len(fields) > 4 and fields[4] else '0.00',
                        'open': fields[5] if len(fields) > 5 and fields[5] else '0.00',
                        'volume': fields[6] if len(fields) > 6 and fields[6] else '0',
                        'high': fields[9] if len(fields) > 9 and fields[9] else '0.00',
                        'low': fields[34] if len(fields) > 34 and fields[34] else '0.00',
                        'pe_dynamic': '',
                        'turnover_rate': fields[38] if len(fields) > 38 and fields[38] else '',
                        'amplitude': fields[43] if len(fields) > 43 and fields[43] else '',
                        'pe_ttm': fields[39] if len(fields) > 39 and fields[39] else '',
                    }
                    all_results[code_num] = result
                    
        except Exception as e:
            print(f"[API 错误] 批次 {i//batch_size + 1} 请求失败: {e}", file=sys.stderr)
            time.sleep(2)
            # Retry once
            try:
                time.sleep(1)
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'Mozilla/5.0')
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read().decode('gbk')
                for line in data.strip().split('\n'):
                    if not line.strip():
                        continue
                    m = re.search(r'v_([a-z]+)(\d+)="(.+)"', line)
                    if not m:
                        continue
                    prefix = m.group(1)
                    code_num = m.group(2)
                    fields = m.group(3).split('~')
                    if len(fields) > 5:
                        result = {
                            'name': fields[1] if len(fields) > 1 else '',
                            'code': fields[2] if len(fields) > 2 else code_num,
                            'price': fields[3] if len(fields) > 3 and fields[3] else '0.00',
                            'prev_close': fields[4] if len(fields) > 4 and fields[4] else '0.00',
                            'open': fields[5] if len(fields) > 5 and fields[5] else '0.00',
                            'volume': fields[6] if len(fields) > 6 and fields[6] else '0',
                            'high': fields[9] if len(fields) > 9 and fields[9] else '0.00',
                            'low': fields[34] if len(fields) > 34 and fields[34] else '0.00',
                            'pe_dynamic': '',
                            'turnover_rate': fields[38] if len(fields) > 38 and fields[38] else '',
                            'amplitude': fields[43] if len(fields) > 43 and fields[43] else '',
                            'pe_ttm': fields[39] if len(fields) > 39 and fields[39] else '',
                        }
                        all_results[code_num] = result
            except Exception as e2:
                print(f"[API 重试失败] {e2}", file=sys.stderr)
    
    return all_results


def try_tx_api_hk(tencent_results, hk_codes_missing):
    """Try fetching HK stock data using alternative Tencent format."""
    if not hk_codes_missing:
        return {}
    
    hk_results = {}
    for code in hk_codes_missing:
        # Try HK format
        url = f"https://qt.gtimg.cn/q=sz{code}"
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read().decode('gbk')
            for line in data.strip().split('\n'):
                m = re.search(r'v_([a-z]+)(\d+)="(.+)"', line)
                if not m:
                    continue
                code_num = m.group(2)
                fields = m.group(3).split('~')
                if len(fields) > 3 and fields[3] and fields[3] != '0.00' and fields[1]:
                    result = {
                        'name': fields[1] if len(fields) > 1 else '',
                        'code': fields[2] if len(fields) > 2 else code_num,
                        'price': fields[3] if len(fields) > 3 and fields[3] else '0.00',
                        'prev_close': fields[4] if len(fields) > 4 and fields[4] else '0.00',
                        'open': fields[5] if len(fields) > 5 and fields[5] else '0.00',
                        'volume': fields[6] if len(fields) > 6 and fields[6] else '0',
                        'high': fields[9] if len(fields) > 9 and fields[9] else '0.00',
                        'low': fields[10] if len(fields) > 10 and fields[10] else '0.00',
                        'pe_dynamic': fields[28] if len(fields) > 28 and fields[28] else '',
                        'turnover_rate': fields[29] if len(fields) > 29 and fields[29] else '',
                        'amplitude': fields[32] if len(fields) > 32 and fields[32] else '',
                        'pe_ttm': fields[37] if len(fields) > 37 and fields[37] else '',
                    }
                    hk_results[code_num] = result
                    break
        except Exception as e:
            pass  # Skip failed HK stocks
    
    return hk_results


# ===== Step 3: Update valuation tracking notes =====
def update_valuation_file(filepath, stock_name, code, market, quote_data):
    """Update the valuation tracking file with new data."""
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if not quote_data:
        # Mark as unavailable
        today_str = TODAY
        # Update data timestamp
        content = re.sub(
            r'> 数据截至：\d{4}-\d{2}-\d{2}',
            f'> 数据截至：{today_str}（数据不可用）',
            content
        )
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return False
    
    price = quote_data.get('price', '0')
    pe_dynamic = quote_data.get('pe_dynamic', '')
    pe_ttm = quote_data.get('pe_ttm', '')
    prev_close = quote_data.get('prev_close', '0')
    high = quote_data.get('high', '0')
    low = quote_data.get('low', '0')
    turnover_rate = quote_data.get('turnover_rate', '')
    amplitude = quote_data.get('amplitude', '')
    volume = quote_data.get('volume', '0')
    name = quote_data.get('name', stock_name)
    
    try:
        price_f = float(price)
        prev_close_f = float(prev_close)
        change_pct = ((price_f - prev_close_f) / prev_close_f * 100) if prev_close_f > 0 else 0
        change_str = f"{change_pct:+.2f}%"
    except (ValueError, ZeroDivisionError):
        change_str = "N/A"
        change_pct = 0
    
    today_str = TODAY
    
    # Determine valuation zone based on PE
    pe_val = None
    try:
        if pe_ttm:
            pe_val = float(pe_ttm)
        elif pe_dynamic:
            pe_val = float(pe_dynamic)
    except ValueError:
        pass
    
    # Update data timestamp
    content = re.sub(
        r'> 数据截至：\d{4}-\d{2}-\d{2}',
        f'> 数据截至：{today_str}',
        content
    )
    
    # Update updated timestamp in frontmatter
    content = re.sub(
        r'updated: \d{4}-\d{2}-\d{2}',
        f'updated: {today_str}',
        content
    )
    
    # Update stock price
    content = re.sub(
        r'\|\s*股价\s*\|\s*¥[\d.]+',
        f'| 股价 | ¥{price}',
        content
    )
    
    # Update PE (TTM)
    pe_ttm_str = pe_ttm if pe_ttm else 'N/A'
    content = re.sub(
        r'\|\s*PE \(TTM\)\s*\|\s*[^\|]+',
        f'| PE (TTM) | {pe_ttm_str}',
        content
    )
    
    # Update PB (leave as N/A since Tencent API doesn't provide PB directly)
    content = re.sub(
        r'\|\s*PB\s*\|\s*[^\|]+',
        '| PB | N/A',
        content
    )
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return {
        'name': stock_name,
        'code': f"{code}.{market}",
        'price': price,
        'pe_ttm': pe_ttm_str,
        'change': change_str,
        'change_pct': change_pct,
        'market': market,
        'high': high,
        'low': low,
        'volume': volume,
        'turnover_rate': turnover_rate,
    }


# ===== Main =====
def main():
    print(f"📊 每日行情更新 | {TODAY}")
    print("=" * 60)
    
    # Step 1: Scan files
    print("\n[Step 1/4] 扫描估值追踪文件...")
    files = scan_valuation_files()
    print(f"  找到 {len(files)} 份估值追踪笔记")
    
    if not files:
        print("  ⚠️ 未找到任何含 #估值追踪 标签的文件")
        print("  尝试扫描目录...")
        # Fallback: look for all -估值追踪.md files
        for root, dirs, filenames in os.walk(TRACKING_DIR):
            for fn in filenames:
                if fn.endswith(".md") and "估值追踪" in fn:
                    fpath = os.path.join(root, fn)
                    files.append(fpath)
        print(f"  找到 {len(files)} 份估值追踪文件")
    
    if not files:
        print("\n❌ 未找到任何估值追踪文件，退出。")
        return
    
    # Step 2: Extract stock codes
    print("\n[Step 2/4] 提取股票代码...")
    stock_info = []  # (dir_name, code, market, filepath)
    for fpath in files:
        dir_name = os.path.basename(os.path.dirname(fpath))
        file_base = os.path.basename(fpath)
        code, market = extract_stock_code(fpath, dir_name)
        if code and market:
            stock_info.append((dir_name, code, market, fpath))
            print(f"  ✓ {dir_name}: {code}.{market}")
        else:
            print(f"  ⚠️ {dir_name}: 无法提取代码，跳过")
    
    if not stock_info:
        print("\n❌ 无法提取任何股票代码，退出。")
        return
    
    # Step 3: Fetch market data
    print(f"\n[Step 3/4] 批量拉取腾讯 API 行情 ({len(stock_info)} 只)...")
    
    # Separate A-share and HK/BJ
    a_share = [(c, m, n, f) for n, c, m, f in stock_info if m in ('SH', 'SZ')]
    hk_stocks = [(c, m, n, f) for n, c, m, f in stock_info if m == 'HK']
    bj_stocks = [(c, m, n, f) for n, c, m, f in stock_info if m == 'BJ']
    
    all_quotes = {}
    
    # Fetch A-shares
    if a_share:
        codes_and_mkts = [(c, m) for c, m, _, _ in a_share]
        print(f"  请求 A 股 ({len(a_share)} 只)...")
        quotes = fetch_tencent_quotes(codes_and_mkts)
        all_quotes.update(quotes)
        for c, m, n, _ in a_share:
            if c in quotes:
                print(f"  ✓ {n} ({c}.{m}): ¥{quotes[c]['price']}")
            else:
                print(f"  ⚠️ {n} ({c}.{m}): 无数据")
    
    # Fetch HK stocks (try API, but data may be delayed)
    if hk_stocks:
        print(f"\n  请求港股 ({len(hk_stocks)} 只)...")
        codes_and_mkts = [(c, m) for c, m, _, _ in hk_stocks]
        quotes = fetch_tencent_quotes(codes_and_mkts)
        all_quotes.update(quotes)
        for c, m, n, _ in hk_stocks:
            if c in quotes:
                print(f"  ✓ {n} ({c}.{m}): ¥{quotes[c]['price']} (港股数据可能延迟)")
            else:
                print(f"  ⚠️ {n} ({c}.{m}): 无数据（港股可能延迟）")
    
    # BJ stocks - skip (梓橦宫)
    if bj_stocks:
        print(f"\n  ⏭️ 北交所 ({len(bj_stocks)} 只) 跳过: 腾讯 API 不返回")
        for n, c, m, _ in bj_stocks:
            print(f"      {n} ({c}.{m})")
    
    # Step 4: Update files
    print(f"\n[Step 4/4] 更新估值追踪笔记...")
    updated = []
    failed = []
    
    for dir_name, code, market, fpath in stock_info:
        if market == 'BJ':
            failed.append((dir_name, code, market, "北交所跳过"))
            continue
        
        quote_data = all_quotes.get(code)
        result = update_valuation_file(fpath, dir_name, code, market, quote_data)
        
        # Also try to find an alternative simpler file name
        dir_path = os.path.dirname(fpath)
        
        if result:
            updated.append(result)
            print(f"  ✓ {dir_name}: ¥{result['price']} ({result['change']})")
        else:
            failed.append((dir_name, code, market, "更新失败"))
            print(f"  ⚠️ {dir_name}: 更新失败")
    
    # ===== Summary Output =====
    print("\n" + "=" * 60)
    print(f"📋 行情摘要 | {TODAY}")
    print("=" * 60)
    
    # Core 5 stocks
    print("\n🔴 核心 5 只")
    print("-" * 60)
    print(f"{'股票':<10} {'代码':<14} {'现价':<10} {'涨跌幅':<10} {'PE(TTM)':<10}")
    print("-" * 60)
    
    core_updated = [u for u in updated if u['name'] in CORE_STOCKS]
    for u in core_updated:
        print(f"{u['name']:<10} {u['code']:<14} ¥{u['price']:<7} {u['change']:<10} {u['pe_ttm']:<10}")
    
    # All other stocks
    others = [u for u in updated if u['name'] not in CORE_STOCKS]
    if others:
        print("\n📌 其他追踪股票")
        print("-" * 60)
        print(f"{'股票':<10} {'代码':<14} {'现价':<10} {'涨跌幅':<10} {'PE(TTM)':<10}")
        print("-" * 60)
        for u in others:
            print(f"{u['name']:<10} {u['code']:<14} ¥{u['price']:<7} {u['change']:<10} {u['pe_ttm']:<10}")
    
    # Anomalies
    anomalies = []
    for u in updated:
        cp = u['change_pct']
        if abs(cp) >= 5:
            anomalies.append(f"  ⚠️ {u['name']} ({u['code']}): {u['change']} 涨跌幅异常")
    
    if anomalies:
        print("\n🚨 异常信号")
        print("-" * 60)
        for a in anomalies:
            print(a)
    
    # Stocks near buy zone (price < PE < threshold, for reference)
    near_buy = []
    for u in updated:
        try:
            pe = float(u['pe_ttm'])
            if 0 < pe < 20:  # PE under 20x could be near buy zone
                near_buy.append(u)
        except (ValueError, TypeError):
            pass
    
    if near_buy:
        print("\n🟢 接近合理偏低区间（PE<20x）")
        print("-" * 60)
        for u in near_buy:
            print(f"  {u['name']} ({u['code']}): PE={u['pe_ttm']}x, 现价¥{u['price']}")
    
    # Summary stats
    print("\n📊 汇总")
    print("-" * 60)
    print(f"  更新成功: {len(updated)} 只")
    print(f"  跳过/失败: {len(failed)} 只")
    if failed:
        print(f"  跳过明细:")
        for n, c, m, reason in failed:
            print(f"    - {n} ({c}.{m}): {reason}")
    
    print(f"\n⏰ 更新时间: {TODAY} 15:30 (A股收盘后)")


if __name__ == "__main__":
    main()
