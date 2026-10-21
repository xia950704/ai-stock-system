#!/usr/bin/env python3
"""
将 v2 五维筛选发现的配对写入 engine.py
========================================
替换旧的主观 PREDEFINED_PAIRS（58对，质量差）为五维筛选通过的配对。

用法:
  python3 utils/add_pairs_v2.py            # 用 v2 发现结果替换 engine 配对
  python3 utils/add_pairs_v2.py --preview   # 只预览不写
"""
import sys, os, json, re
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_FILE = os.path.join(PROJECT_ROOT, 'discovered_pairs_v2.json')
ENGINE_FILE = os.path.join(PROJECT_ROOT, 'strategies', 'pairs', 'engine.py')


def load_discovered():
    if not os.path.exists(RESULTS_FILE):
        print("❌ 无 v2 发现结果，先运行 pairs_discovery_v2.py")
        return []
    with open(RESULTS_FILE, encoding='utf-8') as f:
        return json.load(f)['pairs']


def build_pair_entry(p):
    """生成 engine.py 的 PREDEFINED_PAIRS 条目。"""
    return (f"    ('{p['stock_a']}', '{p['stock_b']}', "
            f"'{p['industry']}', '{p['name_a']}↔{p['name_b']}'),  "
            f"# r={p['correlation']} 协整p={p['coint_p']} 半衰期={p['halflife']}天")


def replace_predefined_pairs(pairs, preview=False):
    """替换 engine.py 的 PREDEFINED_PAIRS 列表为 v2 发现。"""
    with open(ENGINE_FILE, encoding='utf-8') as f:
        content = f.read()

    # 定位 PREDEFINED_PAIRS = [ ... ] 块
    start_marker = 'PREDEFINED_PAIRS = ['
    end_marker = '\n]\n\nFORWARD_PAIRS'

    start = content.find(start_marker)
    end = content.find(end_marker, start)
    if start < 0 or end < 0:
        print("❌ 找不到 PREDEFINED_PAIRS 块")
        return False

    old_block = content[start:end + len(end_marker) + 1]

    # 构建新块
    new_entries = [f"# v2 五维筛选发现的配对（{len(pairs)}对，{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}）"]
    new_entries.append("# 筛选: 相关性>0.6 + 市值比<3 + 波动比<1.5 + 协整p<0.05 + 滚动稳定>60% + 半衰期5-60天")
    new_entries.append("PREDEFINED_PAIRS = [")
    for p in pairs:
        new_entries.append(build_pair_entry(p))
    new_entries.append(']')
    new_block = '\n'.join(new_entries)

    # FORWARD_PAIRS：保留白酒前3对作为前向测试
    forward_pairs = pairs[:5] if len(pairs) >= 5 else pairs
    forward_entries = ["FORWARD_PAIRS = ["]
    for p in forward_pairs:
        forward_entries.append(build_pair_entry(p))
    forward_entries.append(']')

    # 替换 FORWARD_PAIRS 块
    fw_start = content.find('FORWARD_PAIRS = [', end)
    fw_end = content.find('\n]', fw_start)
    if fw_start >= 0 and fw_end >= 0:
        content = content[:fw_start] + '\n'.join(forward_entries) + content[fw_end + 2:]

    # 替换 PREDEFINED_PAIRS 块
    new_content = content[:start] + new_block + content[end + len(end_marker) + 1:]

    if preview:
        print("=== 预览新 PREDEFINED_PAIRS ===")
        print(new_block)
        return True

    with open(ENGINE_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"✅ 已写入 {len(pairs)} 对到 {ENGINE_FILE}")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true', help='只预览不写')
    args = parser.parse_args()

    pairs = load_discovered()
    if not pairs:
        return

    print(f"📋 v2 发现 {len(pairs)} 对配对:")
    for p in pairs:
        print(f"  {p['name_a']}↔{p['name_b']} [{p['industry']}] "
              f"r={p['correlation']} 协整p={p['coint_p']} 半衰期={p['halflife']}天")

    replace_predefined_pairs(pairs, preview=args.preview)


if __name__ == '__main__':
    main()
