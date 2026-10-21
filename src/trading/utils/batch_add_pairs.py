#!/usr/bin/env python3
"""批量添加新发现的配对和股票到系统"""
import sys, os, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.data import STOCK_POOL

# 新发现的股票代码及名称（从Sina获取）
NEW_STOCKS = {
    '002045': '国光电器', '002351': '漫步者',
    '002709': '天赐材料', '002812': '恩捷股份',
    '300676': '华大基因', '300760': '迈瑞医疗', '300783': '三只松鼠',
    '600015': '华夏银行', '600016': '民生银行',
    '600118': '中国卫星',
    '600420': '国药现代', '600422': '昆药集团',
    '600584': '长电科技', '600587': '新华医疗',
    '600809': '山西汾酒',
    '601106': '中国一重', '601166': '兴业银行', '601169': '北京银行',
    '601788': '光大证券', '601818': '光大银行', '601901': '方正证券',
    '603127': '昭衍新药', '603369': '今世缘',
    '603658': '安图生物', '603659': '璞泰来',
    '603719': '良品铺子', '603882': '金域医学', '603986': '兆易创新',
    '688008': '澜起科技', '688041': '海光信息',
    '688202': '美迪西', '688236': '春立医疗', '688276': '百克生物',
}

# 新配对 (stock_a, stock_b, industry, label)
NEW_PAIRS = [
    ('002709', '002812', '新能源', '天赐材料↔恩捷股份'),
    ('603659', '300750', '新能源', '璞泰来↔宁德时代'),
    ('600036', '601166', '银行', '招商银行↔兴业银行'),
    ('600085', '600332', '中药', '同仁堂↔白云山'),
    ('603259', '688202', '医疗服务', '药明康德↔美迪西'),
    ('601788', '601901', '证券', '光大证券↔方正证券'),
    ('600584', '603986', '半导体', '长电科技↔兆易创新'),
    ('603986', '688008', '半导体', '兆易创新↔澜起科技'),
    ('600809', '000596', '白酒', '山西汾酒↔古井贡酒'),
    ('600779', '603369', '白酒', '水井坊↔今世缘'),
    ('600197', '603589', '白酒', '伊力特↔口子窖'),
    ('002709', '300750', '新能源', '天赐材料↔宁德时代'),
    ('688276', '300122', '生物制品', '百克生物↔智飞生物'),
    ('603127', '603259', '医疗服务', '昭衍新药↔药明康德'),
    ('600436', '600976', '中药', '片仔癀↔健民集团'),
    ('603127', '688202', '医疗服务', '昭衍新药↔美迪西'),
    ('600422', '600436', '中药', '昆药集团↔片仔癀'),
    ('688008', '688041', '半导体', '澜起科技↔海光信息'),
    ('601166', '601818', '银行', '兴业银行↔光大银行'),
    ('603658', '300760', '医疗器械', '安图生物↔迈瑞医疗'),
    ('688276', '002007', '生物制品', '百克生物↔华兰生物'),
    ('002045', '002351', '消费电子', '国光电器↔漫步者'),
    ('300676', '603882', '医疗器械', '华大基因↔金域医学'),
    ('600016', '601169', '银行', '民生银行↔北京银行'),
    ('600420', '600587', '化学制药', '国药现代↔新华医疗'),
    ('600015', '601169', '银行', '华夏银行↔北京银行'),
    ('603719', '300783', '食品饮料', '良品铺子↔三只松鼠'),
    ('688236', '300003', '医疗器械', '春立医疗↔乐普医疗'),
    ('600118', '601106', '银行', '中国卫星↔中国一重'),
]

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         '..', 'core', 'data.py')
ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           '..', 'strategies', 'pairs', 'engine.py')

# 1. 添加到 data.py
print(f"📥 添加新股票到股票池...")
with open(DATA_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 找到 STOCK_POOL 的结束位置
end_marker = "    # ========== 配对套利补充股 =========="
pos = content.find(end_marker)
if pos > 0:
    # 在配利补充股后面插入
    insert_pos = content.find("\n}", pos)
    new_entries = "\n    # ========== 自动发现配对（2026-07-16）第二批 =========="
    for code, name in sorted(NEW_STOCKS.items()):
        if code not in STOCK_POOL:
            new_entries += f"\n    '{code}': '{name}',"
    new_entries += "\n"
    content = content[:insert_pos] + new_entries + content[insert_pos:]
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        f.write(content)

# 验证
from core.data import STOCK_POOL
print(f"  ✅ 股票池: {len(STOCK_POOL)} → ", end='')
# 刷新模块
import importlib
importlib.reload(sys.modules['core.data'])
from core.data import STOCK_POOL as SP2
print(f"{len(SP2)} 只")

# 2. 添加到 engine.py
print(f"\n📥 添加新配对到策略引擎...")
with open(ENGINE_PATH, 'r', encoding='utf-8') as f:
    content = f.read()

# 在 PREDEFINED_PAIRS 的 ] 前插入
end_pair_marker = "]\n\n\n# 前向测试专用配对"
pos = content.find(end_pair_marker)
if pos > 0:
    new_section = "\n    # === 自动发现二批（2026-07-16） ===\n"
    for a, b, sector, label in NEW_PAIRS:
        new_section += f"    ('{a}', '{b}', '{sector}', '{label}'),\n"
    content = content[:pos] + new_section + content[pos:]
    with open(ENGINE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  ✅ 添加 {len(NEW_PAIRS)} 对")

# 验证
import importlib
importlib.invalidate_caches()
spec = importlib.util.spec_from_file_location('engine_mod', ENGINE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print(f"  有效配对: {len(mod.PREDEFINED_PAIRS)}")

print(f"\n✅ 全部完成！")
print(f"  新增股票: {len(NEW_STOCKS)} 只")
print(f"  新增配对: {len(NEW_PAIRS)} 对")
print(f"  💡 运行: python3 run.py pairs backtest")