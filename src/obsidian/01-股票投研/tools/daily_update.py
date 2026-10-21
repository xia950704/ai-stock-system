#!/usr/bin/env python3
"""
A股收盘后每日行情更新脚本
扫描 vault 中所有 估值追踪 文件 -> 批量拉取腾讯API行情 -> 更新笔记 -> 输出摘要
"""
import os
import re
import json
import urllib.request
import urllib.error
import datetime
import sys
import time

VAULT_BASE = "/Users/xiashuang/obsidian/all about xia/01-股票投研/股票"
TODAY = datetime.date.today().strftime("%Y-%m-%d")
# 使用最近的交易日（如果是周末则用上周五）
WEEKDAY = datetime.date.today().weekday()
if WEEKDAY >= 5:
    # 周末，用上周五
    days_since_friday = WEEKDAY - 4
    TRADE_DATE = (datetime.date.today() - datetime.timedelta(days=days_since_friday)).strftime("%Y-%m-%d")
else:
    TRADE_DATE = TODAY

def extract_code(content, filename):
    """从文件内容中提取股票代码"""
    # 从标题行提取: # 💰 恒瑞医药 (600276.SH) - 估值追踪
    m = re.search(r'\(([\d]{6}\.(?:SH|SZ|HK)|[\d]{5}\.(?:HK))\)', content)
    if m:
        return m.group(1)
    # 尝试 HK 5位代码
    m = re.search(r'\(([\d]{5}\.HK)\)', content)
    if m:
        return m.group(1)
    # 尝试无后缀
    m = re.search(r'\((\d{6})\)', content)
    if m:
        return m.group(1)
    return None

def tencent_quote_a(code):
    """从腾讯API获取A股行情，返回 {price, change_pct, change_amount, high, low, open, pre_close}"""
    # code format: 600276.SH -> sh600276
    code_num = code.split('.')[0]
    market = code.split('.')[1].lower()
    url = f"https://qt.gtimg.cn/q={market}{code_num}"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Referer': 'https://qt.gtimg.cn/'
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read().decode('gbk')
        
        # Parse: v_sh600276="1~恒瑞医药~48.67~..."
        # 字段以 ~ 分隔
        # A股标准字段（腾讯旧版sina风格）：
        # 0: 股票名称, 1: 代码, 2: 现价, 3: 昨收, 4: 今开, 5: 最高, 6: 最低
        # 32: 涨跌幅, 37: 涨跌额
        parts = data.split('~')
        if len(parts) < 40:
            return None
        
        price = float(parts[3]) if parts[3] else None
        pre_close = float(parts[4]) if parts[4] else None
        open_p = float(parts[5]) if parts[5] else None
        high = float(parts[6]) if parts[6] else None
        low = float(parts[7]) if parts[7] else None
        change_pct = float(parts[32]) if parts[32] else None
        change_amount = float(parts[37]) if parts[37] else None
        
        return {
            'price': price,
            'change_pct': change_pct,
            'change_amount': change_amount,
            'high': high,
            'low': low,
            'open': open_p,
            'pre_close': pre_close
        }
    except Exception as e:
        return None

def tencent_quote_hk(code):
    """从腾讯API获取港股行情"""
    code_num = code.split('.')[0]
    url = f"https://qt.gtimg.cn/q=hk{code_num}"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
            'Referer': 'https://qt.gtimg.cn/'
        })
        resp = urllib.request.urlopen(req, timeout=10)
        data = resp.read().decode('gbk')
        
        # 港股: hk09926 format
        # 字段不同，但我们只需要价格和涨跌幅
        parts = data.split('~')
        if len(parts) < 5:
            return None
        
        # 港股腾讯API: 
        # 0: 市场, 1: 代码, 2: 名称, 3: 现价
        name = parts[2]
        price = float(parts[3]) if parts[3] else None
        
        # 尝试找涨跌幅 - 港股字段不同
        # 通常格式: hk09926="...~名称~现价~..."
        # 现价通常在位置3
        # 涨跌幅可能在后面
        change_pct = None
        change_amount = None
        
        # 尝试解析涨跌幅（位置可能在5-10之间）
        for i in range(5, min(15, len(parts))):
            try:
                val = parts[i].strip()
                if val and '%' in val:
                    change_pct = float(val.replace('%', ''))
                    break
            except Exception as e:
                print(f"⚠️ 涨跌幅解析失败：{e}")
                continue
        
        # 尝试找涨跌额
        for i in range(5, min(15, len(parts))):
            try:
                val = parts[i].strip()
                if val and val.startswith(('-', '+')) and not '%' in val:
                    change_amount = float(val)
                    break
            except Exception as e:
                print(f"⚠️ 涨跌额解析失败：{e}")
                continue
        
        return {
            'price': price,
            'change_pct': change_pct,
            'change_amount': change_amount,
            'high': None,
            'low': None,
            'open': None,
            'pre_close': None
        }
    except Exception as e:
        return None

def update_valuation_file(filepath, stock_name, code, quote_data):
    """更新估值追踪文件中的当前价和涨跌幅"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    price = quote_data['price']
    change_pct = quote_data['change_pct']
    
    # 1. 更新"数据截至"日期
    content = re.sub(
        r'> 数据截至：[\d-]+',
        f'> 数据截至：{TRADE_DATE}',
        content
    )
    
    # 2. 更新当前估值表的股价行
    # | 股价 | ¥48.67 | — | — |
    price_str = f"¥{price:.2f}"
    content = re.sub(
        r'\| 股价 \|.*?¥[\d.]+',
        f'| 股价 | {price_str}',
        content
    )
    
    # 3. 如果有涨跌幅，也更新
    if change_pct is not None:
        # 检查是否有涨跌幅行
        if re.search(r'\| 涨跌幅 \|', content):
            change_str = f"{change_pct:+.2f}%"
            content = re.sub(
                r'\| 涨跌幅 \|.*?[-+]?[\d.]+\%',
                f'| 涨跌幅 | {change_str}',
                content
            )
        # 否则尝试添加到当前估值表
        # 找到 股价 行之后添加涨跌幅行
        else:
            # 在当前估值表最后一行前插入
            pass  # 跳过，不破坏表格结构
    
    # 4. 更新历史估值对比中的当前行
    # | **当前** | **待更新** | **¥48.42** | **待分析** |
    content = re.sub(
        r'\|\s*\*\*当前\*\*\s*\|\s*\*\*.*?\*\*\s*\|\s*\*\*¥[\d.]+\*\*',
        f'| **当前** | **待更新** | **{price_str}**',
        content
    )
    
    # 5. 更新 utm 属性中的 updated 日期
    content = re.sub(
        r'updated: [\d-]+',
        f'updated: {TODAY}',
        content
    )
    
    # 6. 添加更新记录
    # 找到 ## 更新记录 和下面的最新记录
    change_str = f"{change_pct:+.2f}%" if change_pct is not None else "N/A"
    record_entry = f"### {TRADE_DATE}\n- 收盘价：{price_str}（{change_str}）"
    
    content = re.sub(
        r'(## 更新记录\n)',
        f'\\1\n{record_entry}\n',
        content
    )
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, price, change_pct
    else:
        return False, price, change_pct

def main():
    print(f"📊 A股行情日更报告 - {TRADE_DATE}")
    print("=" * 60)
    
    if not os.path.exists(VAULT_BASE):
        print(f"❌ 错误：vault 路径不存在：{VAULT_BASE}")
        sys.exit(1)
    
    # 扫描所有 -估值追踪.md 文件
    val_files = []
    for root, dirs, files in os.walk(VAULT_BASE):
        for f in files:
            if f.endswith('-估值追踪.md') and '(' not in f:
                # 排除带代码的文件名如 恒瑞医药(600276.SH)估值追踪.md
                # 只保留 恒瑞医药-估值追踪.md 这样的纯净文件名
                val_files.append(os.path.join(root, f))
    
    val_files.sort()
    print(f"📁 发现 {len(val_files)} 个估值追踪文件\n")
    
    # 读取所有文件内容提取股票代码
    stock_list = []
    for fp in val_files:
        with open(fp, 'r', encoding='utf-8') as f:
            content = f.read()
        
        stock_name = os.path.basename(os.path.dirname(fp))
        code = extract_code(content, fp)
        
        if code:
            stock_list.append({
                'filepath': fp,
                'name': stock_name,
                'code': code,
                'content': content
            })
        else:
            print(f"⚠️  {stock_name}: 未找到股票代码，跳过")
    
    print(f"🔢 提取到 {len(stock_list)} 个带代码的股票\n")
    
    # 分类
    a_stocks = [s for s in stock_list if s['code'].endswith(('.SH', '.SZ'))]
    hk_stocks = [s for s in stock_list if s['code'].endswith('.HK')]
    bj_stocks = [s for s in stock_list if s['code'].startswith('832') or s['code'].startswith('4') or s['code'].startswith('8')]
    
    print(f"📈 A股: {len(a_stocks)} 只, 港股: {len(hk_stocks)} 只")
    
    # 批量获取行情
    results = []
    errors = []
    
    total = len(a_stocks) + len(hk_stocks)
    
    print(f"\n{'='*60}")
    print(f"📥 开始拉取行情数据...")
    
    # A股
    for s in a_stocks:
        name = s['name']
        code = s['code']
        quote = tencent_quote_a(code)
        
        if quote and quote['price']:
            s['quote'] = quote
            # 尝试更新文件
            updated, price, chg = update_valuation_file(
                s['filepath'], name, code, quote
            )
            results.append({
                'name': name,
                'code': code,
                'price': price,
                'change_pct': chg,
                'updated': updated,
                'market': 'A'
            })
            status = "✅" if updated else "⏭️"
            chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
            print(f"  {status} {name}({code}): ¥{price:.2f} ({chg_str})")
        else:
            errors.append(f"  ❌ {name}({code}): API失败")
            print(f"  ❌ {name}({code}): API获取失败")
            # 重试一次
            print(f"     ↻ 重试...")
            import time
            time.sleep(1)
            quote = tencent_quote_a(code)
            if quote and quote['price']:
                s['quote'] = quote
                updated, price, chg = update_valuation_file(
                    s['filepath'], name, code, quote
                )
                results.append({
                    'name': name,
                    'code': code,
                    'price': price,
                    'change_pct': chg,
                    'updated': updated,
                    'market': 'A'
                })
                chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
                print(f"  ✅ {name}({code}): ¥{price:.2f} ({chg_str}) (重试成功)")
            else:
                errors.append(f"  ❌ {name}({code}): 重试仍失败")
                print(f"  ❌ {name}({code}): 重试仍失败")
    
    # 港股
    for s in hk_stocks:
        name = s['name']
        code = s['code']
        quote = tencent_quote_hk(code)
        
        if quote and quote['price']:
            s['quote'] = quote
            updated, price, chg = update_valuation_file(
                s['filepath'], name, code, quote
            )
            results.append({
                'name': name,
                'code': code,
                'price': price,
                'change_pct': chg,
                'updated': updated,
                'market': 'HK'
            })
            status = "✅" if updated else "⏭️"
            chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
            label = "HK$" if code.endswith('.HK') else "¥"
            print(f"  {status} {name}({code}): HK${price:.2f} ({chg_str})")
        else:
            errors.append(f"  ❌ {name}({code}): API获取失败（港股数据可能延迟）")
            print(f"  ❌ {name}({code}): API获取失败（港股数据可能延迟）")
            # 重试
            time.sleep(1)
            print(f"     ↻ 重试...")
            quote = tencent_quote_hk(code)
            if quote and quote['price']:
                s['quote'] = quote
                updated, price, chg = update_valuation_file(
                    s['filepath'], name, code, quote
                )
                results.append({
                    'name': name,
                    'code': code,
                    'price': price,
                    'change_pct': chg,
                    'updated': updated,
                    'market': 'HK'
                })
                chg_str = f"{chg:+.2f}%" if chg is not None else "N/A"
                print(f"  ✅ {name}({code}): HK${price:.2f} ({chg_str}) (重试成功)")
            else:
                errors.append(f"  ❌ {name}({code}): 重试仍失败（可能停牌/无数据）")
                print(f"  ❌ {name}({code}): 重试仍失败")
    
    # ========== 输出摘要 ==========
    print(f"\n{'='*60}")
    print(f"📊 日更摘要 - {TRADE_DATE}")
    print(f"{'='*60}")
    
    core_5 = ['恒瑞医药', '华东医药', '人福医药', '科伦药业', '药明康德']
    
    # 核心5只
    print(f"\n🔴 核心5只")
    print(f"{'─'*50}")
    core_results = [r for r in results if r['name'] in core_5]
    for r in core_results:
        prefix = "HK$" if r['market'] == 'HK' else "¥"
        chg_indicator = ""
        if r['change_pct'] is not None:
            if r['change_pct'] > 5:
                chg_indicator = " 🚀"
            elif r['change_pct'] > 3:
                chg_indicator = " 📈"
            elif r['change_pct'] < -5:
                chg_indicator = " 💥"
            elif r['change_pct'] < -3:
                chg_indicator = " 📉"
        chg_str = f"{r['change_pct']:+.2f}%" if r['change_pct'] is not None else "N/A"
        print(f"  {r['name']:　<4s} ({r['code']:>10s}): {prefix}{r['price']:<8.2f} {chg_str}{chg_indicator}")
    
    missed_core = [s for s in core_5 if s not in [r['name'] for r in results]]
    for name in missed_core:
        print(f"  {name}: 未获取到数据")
    
    # 全部股票
    print(f"\n📋 全部股票（{len(results)} 只）")
    print(f"{'─'*50}")
    
    # 按涨跌幅排序
    sorted_results = sorted(
        [r for r in results if r['change_pct'] is not None],
        key=lambda x: x['change_pct'],
        reverse=True
    )
    no_data = [r for r in results if r['change_pct'] is None]
    
    for r in sorted_results:
        prefix = "HK$" if r['market'] == 'HK' else "¥"
        chg_str = f"{r['change_pct']:+.2f}%"
        print(f"  {r['name']:　<4s} ({r['code']:>10s}): {prefix}{r['price']:<8.2f} {chg_str}")
    
    for r in no_data:
        prefix = "HK$" if r['market'] == 'HK' else "¥"
        print(f"  {r['name']:　<4s} ({r['code']:>10s}): {prefix}{r['price']:<8.2f} 涨跌幅:N/A")
    
    # 异常信号
    anomalies = []
    for r in results:
        if r['change_pct'] is not None:
            if abs(r['change_pct']) >= 10:
                anomalies.append(f"  ⚠️  {r['name']}({r['code']}): 涨跌幅异常 {r['change_pct']:+.2f}%")
            elif abs(r['change_pct']) >= 5:
                anomalies.append(f"  ⚡ {r['name']}({r['code']}): 大幅波动 {r['change_pct']:+.2f}%")
    
    if anomalies:
        print(f"\n⚠️  异常信号")
        print(f"{'─'*50}")
        for a in anomalies:
            print(a)
    
    if errors:
        print(f"\n❌ 错误信息")
        print(f"{'─'*50}")
        for e in errors:
            print(e)
    
    # 接近买入区间的标注（如果有估值区间数据）
    # 简单标注：估值区间参考表中如果有低估/合理偏低的状态，我们可以根据当前价对比
    # 这里主要是数据输出，不做判断
    
    print(f"\n{'='*60}")
    print(f"📝 文件更新状态")
    print(f"{'─'*50}")
    updated_count = sum(1 for r in results if r['updated'])
    skipped_count = sum(1 for r in results if not r['updated'])
    print(f"  已更新: {updated_count} 只")
    print(f"  无需变更: {skipped_count} 只")
    print(f"  失败: {len(errors)} 只")
    
    print(f"\n{'='*60}")
    print(f"⏰ 报告生成: {TODAY} {datetime.datetime.now().strftime('%H:%M')}")
    
    # 返回摘要用于通知
    summary_lines = []
    # 核心5只
    summary_lines.append(f"核心5只:")
    for r in core_results:
        prefix = "HK$" if r['market'] == 'HK' else "¥"
        chg_str = f"{r['change_pct']:+.2f}%" if r['change_pct'] is not None else "N/A"
        summary_lines.append(f"  {r['name']}:{prefix}{r['price']:.2f}({chg_str})")
    
    for name in missed_core:
        summary_lines.append(f"  {name}:无数据")
    
    # 异常
    for a in anomalies:
        summary_lines.append(a)
    
    if errors:
        summary_lines.append(f"  {len(errors)}只获取失败")
    
    print(f"\n📨 通知摘要:")
    for line in summary_lines:
        print(f"  {line}")

if __name__ == '__main__':
    main()
