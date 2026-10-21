#!/usr/bin/env python3
"""
标准化股票投资笔记 - 第一阶段：数据提取与清洗
===============================================
1. 扫描所有股票目录，提取 stock_code、exchange、sector 等关键字段
2. 从文件名、YAML frontmatter、正文中多维度提取
3. 输出标准化的 JSON 数据

用法：
    python standardize_stock_notes.py --scan
    python standardize_stock_notes.py --process
"""

import os, re, json, sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

VAULT_ROOT = Path("/Users/xiashuang/obsidian/all about xia")
STOCK_DIR = VAULT_ROOT / "01-股票投研" / "股票"
OUTPUT_DIR = VAULT_ROOT / "01-股票投研" / "data" / "standardized"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_stock_code(name, content):
    """从股票名称或内容中提取股票代码"""
    # 从文件名或内容中匹配 6 位代码
    patterns = [
        r'(\d{6})\.(SH|SZ|HK)',  # 600276.SH
        r'(\d{6})',               # 600276
    ]
    
    for pat in patterns:
        match = re.search(pat, name, re.IGNORECASE)
        if match:
            return match.group(0)
        match = re.search(pat, content, re.IGNORECASE)
        if match:
            code = match.group(1) if pat == patterns[0] else match.group(0)
            if len(code) == 6:
                return code
    
    return None


def extract_exchange(code):
    """从股票代码推断交易所"""
    if not code:
        return None
    
    # 港股 0xxxx
    if code.startswith('0') and len(code) == 5:
        return 'HK'
    # A 股 6 开头=沪市，0/3 开头=深市
    if code.startswith('6'):
        return 'SH'
    elif code.startswith('0') or code.startswith('3'):
        return 'SZ'
    elif code.startswith('4') or code.startswith('8'):
        return 'BJ'
    
    return None


def parse_yaml_frontmatter(content):
    """提取 YAML frontmatter"""
    yaml_data = {}
    yaml_match = re.search(r'^---\n(.*?)\n---', content, re.DOTALL)
    if yaml_match:
        yaml_content = yaml_match.group(1)
        for line in yaml_content.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#') and not line.startswith('-'):
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip().strip("'\"")
                if value:
                    yaml_data[key] = value
    
    return yaml_data


def extract_from_content(content, patterns):
    """从正文中提取关键字段"""
    results = {}
    for field, pat in patterns.items():
        match = re.search(pat, content)
        if match:
            results[field] = match.group(1).strip() if match.groups() else match.group(0).strip()
    return results


def scan_stock(stock_folder):
    """扫描单只股票的所有文件"""
    stock_name = stock_folder.name
    
    if not stock_folder.is_dir() or stock_name.startswith('00'):
        return None
    
    # 收集所有 md 文件
    md_files = list(stock_folder.glob('*.md'))
    if not md_files:
        return None
    
    # 合并所有文件内容用于搜索
    all_content = '\n'.join([f.read_text(encoding='utf-8') for f in md_files])
    
    # 找投资笔记文件（最大的是主文件）
    note_files = [f for f in md_files if '投资笔记' in f.name]
    note_file = max(note_files, key=lambda x: x.stat().st_size) if note_files else None
    
    # 提取 YAML frontmatter
    yaml_data = {}
    if note_file:
        with open(note_file, 'r', encoding='utf-8') as f:
            note_content = f.read()
        yaml_data = parse_yaml_frontmatter(note_content)
    
    # 提取 stock_code
    code = extract_stock_code(stock_name, all_content)
    if not code:
        # 尝试从 YAML 的别名中提取
        aliases = yaml_data.get('aliases', '')
        if aliases:
            match = re.search(r'(\d{6})', aliases)
            if match:
                code = match.group(1)
    
    # 推断交易所
    exchange = extract_exchange(code) if code else yaml_data.get('exchange', '')
    
    # 从 YAML 获取其他字段
    sector = yaml_data.get('sector', '')
    status = yaml_data.get('status', '')
    position = yaml_data.get('position', '')
    current_price = yaml_data.get('current_price', '')
    pe_ttm = yaml_data.get('pe_ttm', '')
    created = yaml_data.get('created', '')
    updated = yaml_data.get('updated', '')
    
    # 检查维度文件
    dimensions = {}
    for dim_name in ['估值追踪', '事件时间线', '技术分析', '业务管线', '研发管线']:
        files = list(stock_folder.glob(f'*{dim_name}*.md'))
        dimensions[dim_name] = {
            'exists': len(files) > 0,
            'files': [f.name for f in files]
        }
    
    return {
        'stock_name': stock_name,
        'stock_code': code,
        'exchange': exchange,
        'sector': sector,
        'status': status,
        'position': position,
        'current_price': current_price,
        'pe_ttm': pe_ttm,
        'created': created,
        'updated': updated,
        'note_file': str(note_file.relative_to(VAULT_ROOT)) if note_file else None,
        'dimensions': dimensions,
        'total_files': len(md_files)
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description='标准化股票投资笔记')
    parser.add_argument('--scan', action='store_true', help='扫描所有股票')
    parser.add_argument('--process', action='store_true', help='标准化处理')
    args = parser.parse_args()
    
    if args.scan:
        # 扫描阶段
        print("=" * 60)
        print("股票数据扫描 - 提取标准化字段")
        print("=" * 60)
        
        stocks = []
        for stock_folder in sorted(STOCK_DIR.iterdir()):
            if not stock_folder.is_dir():
                continue
            result = scan_stock(stock_folder)
            if result:
                stocks.append(result)
        
        # 统计
        print(f"\n扫描完成: {len(stocks)} 只股票\n")
        
        stats = {
            'total': len(stocks),
            'has_code': sum(1 for s in stocks if s['stock_code']),
            'has_exchange': sum(1 for s in stocks if s['exchange']),
            'has_sector': sum(1 for s in stocks if s['sector']),
            'has_status': sum(1 for s in stocks if s['status']),
            'has_position': sum(1 for s in stocks if s['position']),
            'has_price': sum(1 for s in stocks if s['current_price']),
            'has_pe': sum(1 for s in stocks if s['pe_ttm']),
        }
        
        print("字段覆盖率:")
        for field, count in stats.items():
            if field == 'total':
                print(f"  {field}: {count}")
            else:
                pct = count / stats['total'] * 100
                print(f"  {field}: {count}/{stats['total']} ({pct:.0f}%)")
        
        # 保存扫描结果
        output_file = OUTPUT_DIR / 'stock_scan.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(stocks, f, ensure_ascii=False, indent=2)
        print(f"\n扫描结果已保存: {output_file}")
        
        # 显示前 10 只
        print("\n前 10 只股票:")
        for i, s in enumerate(stocks[:10], 1):
            code_str = s['stock_code'] or '(无代码)'
            dim_count = sum(1 for d in s['dimensions'].values() if d['exists'])
            print(f"  {i}. {s['stock_name']} ({code_str}) | 维度: {dim_count}/5")
    
    elif args.process:
        print("第二阶段：数据标准化处理")
        print("（需要扫描结果）")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()