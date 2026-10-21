#!/usr/bin/env python3
"""
标准化股票投资笔记 - 深度数据提取
==================================
从多个维度文件（估值追踪、业务管线、投资笔记）中提取关键数据
生成标准化的 JSON 数据表

输出：
- 01-股票投研/data/standardized/stocks.jsonl
- 01-股票投研/data/standardized/stock_summary.md
"""

import os, re, json, sys
from pathlib import Path
from datetime import datetime

VAULT_ROOT = Path("/Users/xiashuang/obsidian/all about xia")
STOCK_DIR = VAULT_ROOT / "01-股票投研" / "股票"
OUTPUT_DIR = VAULT_ROOT / "01-股票投研" / "data" / "standardized"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def read_file_safe(filepath):
    """安全读取文件"""
    try:
        return filepath.read_text(encoding='utf-8')
    except Exception as e:
        return ''


def parse_yaml(content):
    """简单解析 YAML frontmatter"""
    yaml_data = {}
    match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    if match:
        for line in match.group(1).split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#') and not line.startswith('-'):
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip().strip("'\"")
                if value:
                    yaml_data[key] = value
    return yaml_data


def extract_table_value(content, indicator_label, fallback_label=None):
    """从表格中提取特定指标的值"""
    patterns = [
        rf'\|\s*{indicator_label}\s*\|\s*([^|]+)\s*\|',
        rf'\|\s*{fallback_label}\s*\|\s*([^|]+)\s*\|' if fallback_label else None,
    ]
    patterns = [p for p in patterns if p]
    
    for pat in patterns:
        match = re.search(pat, content)
        if match:
            value = match.group(1).strip()
            return value
    return None


def extract_price_pe_from_table(content):
    """从估值追踪文件的表格中提取价格、PE、PB和建仓计划"""
    result = {'price': None, 'pe': None, 'pb': None}
    
    # 方法1：匹配 "| 股价 | ¥54.45 |" 或 "| 股价 | HK$11.330 |"（价格可能在下一列）
    price_match = re.search(r'\|\s*股价\s*\|\s*(?:[^|]+\|)*?\s*(?:¥|HK\$)?\s*(\d{1,4}\.?\d*)\s*\|', content)
    if price_match:
        result['price'] = float(price_match.group(1))
    
    # 方法2：匹配 "收盘价：¥54.45"（更新记录）或 "收 ¥15.92" 或 "PE=10.16"
    if not result['price']:
        price_match2 = re.search(r'收盘价[：:]\s*¥?\s*(\d+\.?\d*)', content)
        if price_match2:
            result['price'] = float(price_match2.group(1))
        else:
            price_match3 = re.search(r'收\s*¥?\s*(\d+\.?\d*)', content)
            if price_match3:
                result['price'] = float(price_match3.group(1))
    
    # 提取PE (TTM) 或 PE
    pe_match = re.search(r'\|\s*PE\s*\(TTM\)\s*\|\s*(\d+\.?\d*)\s*\|', content)
    if pe_match:
        result['pe'] = float(pe_match.group(1))
    elif not result['pe']:
        pe_match2 = re.search(r'\|\s*PE\s*\|\s*(\d+\.?\d*)\s*\|', content)
        if pe_match2:
            result['pe'] = float(pe_match2.group(1))
    
    # 提取PB
    pb_match = re.search(r'\|\s*PB\s*\|\s*(\d+\.?\d*)\s*\|', content)
    if pb_match:
        result['pb'] = float(pb_match.group(1))
    
    # 提取建仓计划
    buy_range = re.search(r'目标买入区间\s*\|\s*\*{0,2}([^\*|\n]+)\*{0,2}\s*\|', content)
    if buy_range:
        result['buy_range'] = buy_range.group(1).strip()
    
    sell_range = re.search(r'目标卖出区间\s*\|\s*\*{0,2}([^\*|\n]+)\*{0,2}\s*\|', content)
    if sell_range:
        result['sell_range'] = sell_range.group(1).strip()
    
    first_pos = re.search(r'第一笔仓位\s*\|\s*\*{0,2}([^\*|\n]+)\*{0,2}\s*\|', content)
    if first_pos:
        result['first_position'] = first_pos.group(1).strip()
    
    return result


def extract_sector_from_pipelines(stock_folder):
    """从股票文件夹中所有md文件提取行业/板块信息"""
    md_files = list(stock_folder.glob('*.md'))
    if not md_files:
        return None
    
    all_content = '\n'.join(read_file_safe(f) for f in md_files)
    
    # 常见医药板块关键词（按优先级排列）
    sectors = [
        ('CXO', ['CXO', 'CRO', 'CDMO', '医药外包', '合同研发']),
        ('疫苗', ['疫苗', '血制品', '血液制品']),
        ('零售', ['零售', '药房', '连锁药店', '连锁药']),
        ('中药', ['中药', '中成药', '中药龙头', '中药企业']),
        ('医疗器械', ['医疗器械', '器械', '心血管器械', '体外诊断', 'IVD', '诊断设备']),
        ('眼科', ['眼科', '爱尔眼科', '屈光']),
        ('创新药', ['创新药', 'biotech', 'biotech', '单抗', '双抗', 'ADC', 'PD-1', '免疫治疗', '靶向药']),
        ('麻醉药', ['麻醉药', '麻醉']),
        ('医药商业', ['医药商业', '流通', '分销']),
        ('医美', ['医美', '美容整形', '玻尿酸']),
        ('消费', ['百润', '预调酒', '酒类']),
        ('抗生素', ['抗生素']),
    ]
    
    for sector, keywords in sectors:
        for kw in keywords:
            if kw.lower() in all_content.lower():
                return sector
    
    return None


def extract_event_count(stock_folder):
    """从事件时间线文件中提取事件数量"""
    event_files = list(stock_folder.glob('*事件时间线*.md'))
    if not event_files:
        return 0
    
    content = read_file_safe(event_files[0])
    table_lines = [l for l in content.split('\n') if l.strip().startswith('|') and '日期' not in l and '------' not in l and '待补充' not in l]
    return len(table_lines)


def extract_exchange_from_code(code_num):
    """从纯数字代码推断交易所"""
    if not code_num:
        return None
    # 5 位 0 开头 → 港股
    if len(code_num) == 5 and code_num.startswith('0'):
        return 'HK'
    # 6 位 6 开头 → 沪市主板/科创板
    if len(code_num) == 6 and code_num.startswith('6'):
        return 'SH'
    # 6 位 0/3 开头 → 深市主板/创业板
    if len(code_num) == 6 and code_num.startswith(('0', '3')):
        return 'SZ'
    # 6 位 8/9 开头 → 北交所
    if len(code_num) == 6 and code_num.startswith(('8', '9')):
        return 'BJ'
    # 4/5 位 4/8 开头 → 北交所
    if len(code_num) in (4, 5) and code_num[0] in ('4', '8'):
        return 'BJ'
    return None


def extract_stock_code(content, note_file=None):
    """提取股票代码 - 优先从文件名/YAML，再匹配内容"""
    # 1. 优先从文件名提取（如 "恒瑞医药(600276.SH)投资笔记.md"）
    if note_file:
        # 匹配完整格式：代码 + 交易所后缀
        filename_match = re.search(r'(\d{5,6}\.(SH|SZ|HK|BJ))', note_file.name, re.IGNORECASE)
        if filename_match:
            return filename_match.group(1)
        # 匹配纯数字代码
        filename_match = re.search(r'(\d{5,6})', note_file.name)
        if filename_match:
            code = filename_match.group(1)
            # 从文件名推断交易所
            if 'HK' in note_file.name.upper():
                return f"{code}.HK"
            elif 'SH' in note_file.name.upper() or code.startswith('6'):
                return f"{code}.SH"
            elif 'SZ' in note_file.name.upper() or code.startswith(('0', '3')):
                return f"{code}.SZ"
            elif 'BJ' in note_file.name.upper() or code.startswith(('8', '9')):
                return f"{code}.BJ"
            return code
    
    # 2. 从内容中匹配 stock_code 字段
    # 2. 从内容中匹配 stock_code 字段
    stock_code_match = re.search(r'stock_code[:\s]+(\d{5,6}\.(SH|SZ|HK|BJ))', content, re.IGNORECASE)
    if stock_code_match:
        return stock_code_match.group(1)
    stock_code_match = re.search(r'stock_code[:\s]+(\d{5,6})', content)
    if stock_code_match:
        code = stock_code_match.group(1)
        if code.startswith('0') and len(code) == 5:
            return f"{code}.HK"
        elif len(code) == 6 and code.startswith('6'):
            return f"{code}.SH"
        elif len(code) == 6 and code.startswith(('0', '3')):
            return f"{code}.SZ"
        elif len(code) == 6 and code.startswith(('8', '9')):
            return f"{code}.BJ"
        return code
    
    # 3. 从内容中匹配括号内的代码（如 "恒瑞医药 (600276.SH)"）
    bracket_match = re.search(r'\((\d{5,6}\.(SH|SZ|HK|BJ))\)', content, re.IGNORECASE)
    if bracket_match:
        return bracket_match.group(1)
    bracket_match = re.search(r'\((\d{5,6})\)', content)
    if bracket_match:
        code = bracket_match.group(1)
        if code.startswith('0') and len(code) == 5:
            return f"{code}.HK"
        elif len(code) == 6 and code.startswith('6'):
            return f"{code}.SH"
        elif len(code) == 6 and code.startswith(('0', '3')):
            return f"{code}.SZ"
        elif len(code) == 6 and code.startswith(('8', '9')):
            return f"{code}.BJ"
        return code
    
    # 4. 匹配 6 位代码（A 股）
    a_share_match = re.search(r'(?<!\d)(6\d{5}|0\d{5}|3\d{5})', content)
    if a_share_match:
        code = a_share_match.group(1)
        if code.startswith('6'):
            return f"{code}.SH"
        elif code.startswith('0') or code.startswith('3'):
            return f"{code}.SZ"
        return code
    
    # 5. 匹配北交所 6 位代码
    bj_match = re.search(r'(?<!\d)(8\d{5}|9\d{5})', content)
    if bj_match:
        return f"{bj_match.group(1)}.BJ"
    
    # 6. 匹配 5 位代码（港股）
    hk_match = re.search(r'(?<!\d)0\d{4}(?!\d)', content)
    if hk_match:
        return f"{hk_match.group(0)}.HK"
    
    return None


def process_stock(stock_folder):
    """处理单只股票，提取所有维度数据"""
    stock_name = stock_folder.name
    
    # 收集所有 md 文件
    md_files = list(stock_folder.glob('*.md'))
    if not md_files:
        return None
    
    # 合并内容
    all_content = '\n'.join(read_file_safe(f) for f in md_files)
    
    # 找投资笔记文件
    note_files = [f for f in md_files if '投资笔记' in f.name]
    note_file = max(note_files, key=lambda x: x.stat().st_size) if note_files else None
    
    # 提取 YAML
    yaml_data = {}
    if note_file:
        yaml_data = parse_yaml(read_file_safe(note_file))
    # 提取股票代码
    code = extract_stock_code(all_content, note_file)
    
    # 推断交易所
    exchange = extract_exchange_from_code(code.split(".")[0]) if code else None
    if not exchange:
        exchange = yaml_data.get('exchange', '')
    
    # 从估值追踪文件提取价格/PE/PB（尝试所有估值追踪文件，直到找到数据）
    valuation_files = list(stock_folder.glob('*估值追踪*.md'))
    price_data = {}
    for val_file in valuation_files:
        val_content = read_file_safe(val_file)
        temp_data = extract_price_pe_from_table(val_content)
        if temp_data.get('price') is not None:
            price_data = temp_data
            break
    # 如果还没找到，用第一个文件（可能只有PE无price）
    if not price_data and valuation_files:
        val_content = read_file_safe(valuation_files[0])
        price_data = extract_price_pe_from_table(val_content)
    
    # 提取行业
    sector = extract_sector_from_pipelines(stock_folder) or yaml_data.get('sector', '')
    
    # 提取事件数量
    event_count = extract_event_count(stock_folder)
    
    # 检查维度文件完整性
    dimensions = {
        '估值追踪': len(list(stock_folder.glob('*估值追踪*.md'))) > 0,
        '事件时间线': len(list(stock_folder.glob('*事件时间线*.md'))) > 0,
        '技术分析': len(list(stock_folder.glob('*技术分析*.md'))) > 0,
        '业务管线': len(list(stock_folder.glob('*业务管线*.md'))) > 0,
        '研发管线': len(list(stock_folder.glob('*研发管线*.md'))) > 0,
    }
    
    # 组合所有数据
    result = {
        'stock_name': stock_name,
        'stock_code': code,
        'exchange': exchange,
        'sector': sector,
        'status': yaml_data.get('status', ''),
        'position': yaml_data.get('position', ''),
        'current_price': price_data.get('price'),
        'pe_ttm': price_data.get('pe'),
        'pb': price_data.get('pb'),
        'buy_range': price_data.get('buy_range'),
        'sell_range': price_data.get('sell_range'),
        'event_count': event_count,
        'total_files': len(md_files),
        'dimensions': dimensions,
        'has_price_data': price_data.get('price') is not None,
        'has_valuation_plan': bool(price_data.get('buy_range')),
        'created': yaml_data.get('created', ''),
        'updated': yaml_data.get('updated', ''),
    }
    
    return result


def main():
    stocks = []
    
    print("=" * 60)
    print("深度数据提取 - 标准化股票投资笔记")
    print("=" * 60)
    
    for stock_folder in sorted(STOCK_DIR.iterdir()):
        if not stock_folder.is_dir() or stock_folder.name.startswith('00'):
            continue
        
        result = process_stock(stock_folder)
        if result:
            stocks.append(result)
    
    print(f"\n处理完成: {len(stocks)} 只股票\n")
    
    # 统计
    stats = {
        'total': len(stocks),
        'has_code': sum(1 for s in stocks if s['stock_code']),
        'has_exchange': sum(1 for s in stocks if s['exchange']),
        'has_sector': sum(1 for s in stocks if s['sector']),
        'has_price': sum(1 for s in stocks if s['has_price_data']),
        'has_plan': sum(1 for s in stocks if s['has_valuation_plan']),
        'has_events': sum(1 for s in stocks if s['event_count'] > 0),
        'all_dimensions': sum(1 for s in stocks if all(s['dimensions'].values())),
    }
    
    print("字段覆盖率:")
    for field, count in stats.items():
        if field == 'total':
            print(f"  {field}: {count}")
        else:
            pct = count / stats['total'] * 100 if stats['total'] > 0 else 0
            print(f"  {field}: {count}/{stats['total']} ({pct:.0f}%)")
    
    # 保存 JSONL
    jsonl_file = OUTPUT_DIR / 'stocks.jsonl'
    with open(jsonl_file, 'w', encoding='utf-8') as f:
        for s in stocks:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')
    print(f"\n数据已保存: {jsonl_file}")
    
    # 生成汇总报告
    md_file = OUTPUT_DIR / 'stock_summary.md'
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write("# 股票投资笔记 - 标准化数据汇总\n\n")
        f.write(f"> 数据截至: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"## 总览\n\n")
        f.write(f"- **股票总数**: {stats['total']} 只\n")
        f.write(f"- **有代码**: {stats['has_code']} 只 ({stats['has_code']/stats['total']*100:.0f}%)\n")
        f.write(f"- **有行业**: {stats['has_sector']} 只 ({stats['has_sector']/stats['total']*100:.0f}%)\n")
        f.write(f"- **有价格数据**: {stats['has_price']} 只 ({stats['has_price']/stats['total']*100:.0f}%)\n")
        f.write(f"- **有建仓计划**: {stats['has_plan']} 只 ({stats['has_plan']/stats['total']*100:.0f}%)\n\n")
        
        f.write("## 按交易所分布\n\n")
        exchanges = {}
        for s in stocks:
            ex = s['exchange'] or 'Unknown'
            exchanges[ex] = exchanges.get(ex, 0) + 1
        for ex, count in sorted(exchanges.items()):
            f.write(f"- **{ex}**: {count} 只\n")
        f.write("\n")
        
        f.write("## 按行业分布\n\n")
        sectors = {}
        for s in stocks:
            sec = s['sector'] or '未分类'
            sectors[sec] = sectors.get(sec, 0) + 1
        for sec, count in sorted(sectors.items(), key=lambda x: -x[1]):
            f.write(f"- **{sec}**: {count} 只\n")
        f.write("\n")
        
        f.write("## 有价格数据的股票\n\n")
        f.write("| 股票名称 | 代码 | 交易所 | 当前价 | PE | PB | 买入区间 |\n")
        f.write("|---------|------|--------|--------|----|----|--------|\n")
        for s in stocks:
            if s['has_price_data']:
                f.write(f"| {s['stock_name']} | {s['stock_code']} | {s['exchange']} | {s['current_price']:.2f} | {s['pe_ttm'] or '-'} | {s['pb'] or '-'} | {s['buy_range'] or '-'} |\n")
        f.write("\n")
    
    print(f"汇总报告已保存: {md_file}")
    
    # 显示前10只
    print("\n前10只股票详情:")
    for i, s in enumerate(stocks[:10], 1):
        price_str = f"¥{s['current_price']:.2f}" if s['has_price_data'] else "无数据"
        print(f"  {i}. {s['stock_name']} ({s['stock_code']}) | {s['exchange']} | {price_str}")


if __name__ == '__main__':
    main()