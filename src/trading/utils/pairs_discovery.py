#!/usr/bin/env python3
"""
配对自动发现系统
=================
先扫后跟——一次性扫描全行业股票，自动发现强相关配对。

工作流:
  1️⃣ 获取行业列表 → 选择要扫描的行业
  2️⃣ 获取该行业全部成分股代码
  3️⃣ 批量拉取价格数据
  4️⃣ 计算全排列相关性矩阵
  5️⃣ 输出强相关配对（corr > 0.8）
  6️⃣ 用户选择→添加到永久股票池

用法:
  python3 utils/pairs_discovery.py                       # 交互式扫描
  python3 utils/pairs_discovery.py --list-industries     # 列出所有行业
  python3 utils/pairs_discovery.py --scan 医药生物       # 扫描指定行业
  python3 utils/pairs_discovery.py --scan-all            # 扫描全部行业（耗时）
  python3 utils/pairs_discovery.py --results             # 查看发现结果
  python3 utils/pairs_discovery.py --add-top 10          # 添加TopN配对到股票池
"""
import sys, os, json, time, argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.data import fetch_a_stock_data, STOCK_POOL
import numpy as np
import pandas as pd

RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'discovered_pairs.json')
DATA_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              '..', 'reports', 'discovery_cache')
os.makedirs(DATA_CACHE_DIR, exist_ok=True)

# 扫描配置
MIN_CORRELATION = 0.80       # 最小相关系数
MIN_DATA_DAYS = 100          # 最少需要多少天数据
MAX_STOCKS_PER_INDUSTRY = 30 # 每行业最多扫描多少只（防止过大行业太慢）
API_DELAY = 0.15             # API请求间隔


def get_all_stocks():
    """
    从Sina获取所有A股股票代码和名称
    返回: [(code, name), ...]
    """
    import requests
    headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
    all_stocks = []

    try:
        for page in range(1, 60):  # max 60页 × 100 = 6000只
            url = ('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
                   'Market_Center.getHQNodeData')
            params = {'page': str(page), 'num': '100', 'sort': 'symbol',
                      'asc': '1', 'node': 'hs_a', 'symbol': '', '_': ''}
            r = requests.get(url, params=params, headers=headers, timeout=10)
            data = r.json()
            if not isinstance(data, list) or len(data) == 0:
                break
            for item in data:
                code = str(item.get('code', ''))
                name = str(item.get('name', '')).strip()
                if code and name:
                    all_stocks.append((code, name))
            if len(data) < 100:
                break
        return all_stocks
    except Exception as e:
        print(f"  ⚠️  获取股票列表失败: {e}")
        return []


# 行业关键词映射
INDUSTRY_KEYWORDS = {
    '中药': ['同仁堂', '片仔癀', '云南白药', '白云山', '以岭', '天士力', '华润三九',
             '东阿阿胶', '马应龙', '江中', '健民', '太极', '千金', '步长', '康恩贝',
             '济川', '三精', '九芝堂', '广誉远', '白云山', '仁和', '华润', '昆药',
             '康缘', '葵花', '羚锐', '精华制药', '佛慈', '佐力', '盘龙'],
    '化学制药': ['恒瑞', '恩华', '人福', '科伦', '贝达', '丽珠', '海正', '普洛',
                '奥翔', '华海', '信立泰', '华润双鹤', '华北', '东北', '新华',
                '现代', '联邦', '鲁抗', '海思科', '亿帆', '翰宇', '仙琚'],
    '生物制品': ['智飞', '沃森', '华兰', '康泰', '万泰', '长春高新', '通化东宝',
                '甘李', '我武', '百克', '欧林', '金迪克'],
    '医疗器械': ['迈瑞', '联影', '鱼跃', '乐普', '微创', '威高', '健帆', '达安',
                '华大', '金域', '迪安', '安图', '新产业', '惠泰', '心脉',
                '南微', '凯利泰', '大博', '春立', '三友'],
    '医疗服务': ['药明', '泰格', '康龙', '凯莱英', '九州', '博腾', '昭衍',
                '美迪西', '皓元', '百诚', '阳光', '爱尔', '通策', '国际医学',
                '信邦', '创新医疗'],
    '医药商业': ['上海医药', '国药一致', '国药股份', '九州通', '大参林', '老百姓',
                '一心堂', '益丰', '健之佳', '漱玉'],
    '白酒': ['茅台', '五粮液', '泸州老窖', '洋河', '山西汾酒', '古井贡',
             '水井坊', '酒鬼酒', '舍得', '迎驾', '口子窖', '今世缘',
             '金徽', '伊力特', '老白干', '顺鑫'],
    '食品饮料': ['伊利', '蒙牛', '海天', '双汇', '安井', '绝味', '桃李',
                 '三全', '洽洽', '良品', '三只', '汤臣', '东鹏'],
    '白色家电': ['美的', '格力', '海尔', '海信', '长虹', 'TCL', '小熊',
                '九阳', '苏泊尔', '老板', '华帝', '万和', '浙江美大'],
    '消费电子': ['立讯', '歌尔', '蓝思', '领益', '传音', '安克', '漫步者',
                '国光', '共达', '佳禾'],
    '安防': ['海康', '大华', '千方', '中威', '高新兴', '英飞拓', '世纪瑞尔'],
    '半导体': ['中芯', '韦尔', '北方华创', '中微', '华大九天', '长电',
              '兆易', '紫光', '卓胜', '澜起', '寒武', '海光', '龙芯'],
    '银行': ['招商', '兴业', '工商', '建设', '农业', '中国', '交通',
             '浦发', '民生', '平安', '中信', '光大', '华夏', '北京'],
    '证券': ['中信', '华泰', '中金', '广发', '招商', '东方', '国泰',
             '海通', '申万', '兴业', '光大', '方正'],
    '新能源': ['宁德', '比亚迪', '隆基', '通威', '阳光', '亿纬', '国轩',
               '天赐', '恩捷', '璞泰来', '先导', '晶澳', '天合'],
}
# 反向映射：股票名→行业
STOCK_TO_INDUSTRY = {}
for ind, names in INDUSTRY_KEYWORDS.items():
    for n in names:
        STOCK_TO_INDUSTRY[n] = ind


def classify_stock(code, name):
    """通过名称关键词匹配行业"""
    for keyword, industry in STOCK_TO_INDUSTRY.items():
        if keyword in name:
            return industry
    return None


def get_industry_stocks(industry_name):
    """
    通过关键词匹配获取某行业成分股
    先从Sina拉全量列表，再按行业关键词过滤
    结果缓存到文件避免重复请求
    """
    cache_file = os.path.join(DATA_CACHE_DIR, 'all_stocks_cache.json')

    # 读取缓存
    all_stocks = None
    if os.path.exists(cache_file):
        cache_age = time.time() - os.path.getmtime(cache_file)
        if cache_age < 86400:  # 缓存24小时
            with open(cache_file, 'r', encoding='utf-8') as f:
                all_stocks = json.load(f)

    if all_stocks is None:
        print(f"  📡 从Sina获取全市场股票列表...")
        raw_stocks = get_all_stocks()
        if not raw_stocks:
            return []

        # 缓存
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(raw_stocks, f, ensure_ascii=False)
        all_stocks = raw_stocks
        print(f"  ✅ 共 {len(all_stocks)} 只")

    # 按行业过滤
    result = []
    for code, name in all_stocks:
        ind = classify_stock(code, name)
        if ind == industry_name:
            result.append((code, name))

    return result


def get_industries():
    """获取行业列表（基于关键词定义）"""
    return list(INDUSTRY_KEYWORDS.keys())


def fetch_price_data_batch(stocks, max_stocks=MAX_STOCKS_PER_INDUSTRY):
    """
    批量拉取价格数据
    返回: {code: price_series}
    """
    result = {}
    total = min(len(stocks), max_stocks)

    for i, (code, name) in enumerate(stocks[:max_stocks]):
        print(f"    [{i+1}/{total}] {code} ({name})...", end=' ')
        df = fetch_a_stock_data(code)
        if df is not None and len(df) >= MIN_DATA_DAYS:
            result[code] = {
                'name': name,
                'series': df['收盘'].values,
                'dates': df.index,
                'days': len(df)
            }
            print(f"✅ {len(df)}天")
        else:
            print(f"❌ 数据不足")
        time.sleep(API_DELAY)

    return result


def compute_correlations(price_data, industry_name, min_corr=MIN_CORRELATION):
    """
    计算行业内的全排列相关系数
    返回: [(stock_a, stock_b, corr, overlap_days), ...]
    """
    codes = list(price_data.keys())
    pairs = []

    total_pairs = len(codes) * (len(codes) - 1) // 2
    print(f"\n    📐 计算 {total_pairs} 个配对相关性...")

    count = 0
    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            code_a = codes[i]
            code_b = codes[j]

            # 对齐日期
            series_a = pd.Series(price_data[code_a]['series'],
                                 index=price_data[code_a]['dates'])
            series_b = pd.Series(price_data[code_b]['series'],
                                 index=price_data[code_b]['dates'])

            aligned = pd.concat([series_a, series_b], axis=1, sort=True).dropna()
            if len(aligned) < MIN_DATA_DAYS:
                continue

            corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])

            # 也计算对数价差的标准差（判断是否适合配对交易）
            log_spread = np.log(aligned.iloc[:, 0]) - np.log(aligned.iloc[:, 1])
            spread_std = log_spread.std()

            if corr > min_corr:
                pairs.append({
                    'stock_a': code_a,
                    'name_a': price_data[code_a]['name'],
                    'stock_b': code_b,
                    'name_b': price_data[code_b]['name'],
                    'industry': industry_name,
                    'correlation': round(corr, 4),
                    'spread_std': round(spread_std, 4),
                    'overlap_days': len(aligned),
                    'price_a': round(float(aligned.iloc[-1, 0]), 2),
                    'price_b': round(float(aligned.iloc[-1, 1]), 2),
                })

            count += 1
            if count % 50 == 0:
                print(f"      ... 已计算 {count}/{total_pairs}, 发现 {len(pairs)} 对")

    return sorted(pairs, key=lambda x: x['correlation'], reverse=True)


def scan_industry(industry_name, max_stocks=MAX_STOCKS_PER_INDUSTRY):
    """扫描单个行业"""
    print(f"\n{'='*55}")
    print(f"  🔍 扫描行业: {industry_name}")
    print(f"{'='*55}")

    print(f"  📋 获取成分股...")
    stocks = get_industry_stocks(industry_name)
    if not stocks:
        print(f"  ❌ 未获取到成分股")
        return []

    print(f"  ✅ 共 {len(stocks)} 只成分股，取前{max_stocks}只扫描")

    # 批量拉取价格
    price_data = fetch_price_data_batch(stocks, max_stocks)
    valid = len(price_data)
    print(f"\n  ✅ 成功获取 {valid}/{max_stocks} 只股票数据")

    if valid < 2:
        print(f"  ⚠️  有效数据不足2只，跳过")
        return []

    # 计算相关性
    pairs = compute_correlations(price_data, industry_name)
    print(f"\n  📊 发现 {len(pairs)} 个强相关配对 (corr > {MIN_CORRELATION})")

    # 输出Top 10
    if pairs:
        print(f"\n  🏆 Top 10 配对:")
        print(f"  {'配对':<30s} {'相关性':>8s} {'价差σ':>8s} {'天数':>5s}")
        print(f"  {'─'*55}")
        for p in pairs[:10]:
            print(f"  {p['name_a']}↔{p['name_b']:<15s} "
                  f"{p['correlation']:.3f}    "
                  f"{p['spread_std']:.3f}    "
                  f"{p['overlap_days']}")

    return pairs


def scan_all_industries(max_industries=10):
    """扫描全部行业（可指定最大数量）"""
    print(f"\n{'='*55}")
    print(f"  🔍 全行业扫描（最多{max_industries}个行业）")
    print(f"{'='*55}")

    industries = get_industries()
    print(f"  📋 共 {len(industries)} 个行业板块")

    all_pairs = []
    for i, ind in enumerate(industries[:max_industries]):
        pairs = scan_industry(ind)
        all_pairs.extend(pairs)

        # 保存中间结果
        save_results(all_pairs)
        print(f"\n  📊 累计发现 {len(all_pairs)} 对")

    # 最终排名
    all_pairs = sorted(all_pairs, key=lambda x: x['correlation'], reverse=True)
    save_results(all_pairs)

    print(f"\n{'='*55}")
    print(f"  🏆 全行业扫描完成")
    print(f"  扫描行业: {min(max_industries, len(industries))}")
    print(f"  发现配对: {len(all_pairs)}")
    if all_pairs:
        print(f"\n  Top 20 全局配对:")
        for i, p in enumerate(all_pairs[:20], 1):
            print(f"  {i:2d}. {p['name_a']:<8s}↔{p['name_b']:<8s} "
                  f"[{p['industry']}] r={p['correlation']:.3f}")

    return all_pairs


def save_results(pairs):
    """保存发现结果"""
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'total_pairs': len(pairs),
            'min_correlation': MIN_CORRELATION,
            'pairs': pairs
        }, f, indent=2, ensure_ascii=False)


def load_results():
    """加载发现结果"""
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE, encoding='utf-8') as f:
            return json.load(f)
    return None


def show_results():
    """显示已发现的结果"""
    data = load_results()
    if not data:
        print("  ⚠️  暂无发现结果，请先运行扫描")
        return

    pairs = data['pairs']
    print(f"\n{'='*55}")
    print(f"  📊 已发现配对: {data['total_pairs']} 对")
    print(f"  扫描时间: {data['scan_time']}")
    print(f"{'='*55}")

    # 按行业分组
    industries = {}
    for p in pairs:
        industries.setdefault(p['industry'], []).append(p)

    for ind, ps in sorted(industries.items()):
        print(f"\n  [{ind}] ({len(ps)}对)")
        for p in ps[:5]:  # 每行业只显示前5
            corr_marker = "🟢" if p['correlation'] > 0.9 else "🟡"
            print(f"  {corr_marker} {p['name_a']:<8s}↔{p['name_b']:<8s} "
                  f"r={p['correlation']:.3f} σ={p['spread_std']:.3f}")
        if len(ps) > 5:
            print(f"    ... 还有 {len(ps)-5} 对")

    # 汇总统计
    print(f"\n  📈 相关性分布:")
    for threshold in [0.95, 0.90, 0.85, 0.80]:
        count = sum(1 for p in pairs if p['correlation'] >= threshold)
        bar = "█" * count
        print(f"    r>={threshold:.2f}: {count:3d}对 {bar}")


def add_top_pairs_to_pool(n=10):
    """
    将Top N配对添加到永久股票池
    写入 data.py 格式的代码
    """
    data = load_results()
    if not data:
        print("  ⚠️  暂无发现结果")
        return

    pairs = data['pairs']
    top_pairs = pairs[:n]

    # 提取所有不重复的股票代码
    new_stocks = {}
    for p in top_pairs:
        if p['stock_a'] not in STOCK_POOL:
            new_stocks[p['stock_a']] = p['name_a']
        if p['stock_b'] not in STOCK_POOL:
            new_stocks[p['stock_b']] = p['name_b']

    if not new_stocks:
        print("  ✅ 所有股票已在股票池中")
        return

    print(f"\n{'='*55}")
    print(f"  📥 添加 {len(new_stocks)} 只新股票到股票池")
    print(f"{'='*55}")
    for code, name in new_stocks.items():
        print(f"  + {code} ({name})")

    # 生成添加到 data.py 的代码
    print(f"\n  将以下代码添加到 core/data.py 的 STOCK_POOL:")
    print(f"\n  # ========== 自动发现配对（{datetime.now().strftime('%Y-%m-%d')}） ==========")
    for code, name in sorted(new_stocks.items()):
        print(f"  '{code}': '{name}',")

    # 自动添加到 data.py
    data_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'core', 'data.py')

    with open(data_path, 'a', encoding='utf-8') as f:
        f.write(f"\n# ========== 自动发现配对（{datetime.now().strftime('%Y-%m-%d')}） ==========\n")
        for code, name in sorted(new_stocks.items()):
            f.write(f"    '{code}': '{name}',\n")

    print(f"\n  ✅ 已自动添加到 {data_path}")

    # 生成引擎配对定义（追加到engine.py）
    engine_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'strategies', 'pairs', 'engine.py')

    # 读取发现的配对，生成PREDEFINED_PAIRS新条目
    pair_entries = []
    added_stocks_set = set(new_stocks.keys())
    for p in top_pairs:
        if p['stock_a'] in added_stocks_set or p['stock_b'] in added_stocks_set:
            pair_entries.append(
                f"    ('{p['stock_a']}', '{p['stock_b']}', "
                f"'{p['industry']}', '{p['name_a']}↔{p['name_b']}'),"
            )

    print(f"\n  以下配对可添加到 strategies/pairs/engine.py:")
    print(f"  # --- 自动发现（{datetime.now().strftime('%Y-%m-%d')}） ---")
    for e in pair_entries[:10]:
        print(f"  {e}")
    print(f"  {'':>2}... 共 {len(pair_entries)} 对")

    # 自动追加
    with open(engine_path, 'r+', encoding='utf-8') as f:
        content = f.read()
        insert_marker = "# ==================== 配对定义 ===================="
        insert_pos = content.find(insert_marker)
        if insert_pos > 0:
            # 找到PREDEFINED_PAIRS列表的结束位置，在末尾插入
            end_marker = "# 前向测试专用配对"
            end_pos = content.find(end_marker)
            if end_pos > 0:
                new_section = f"\n# --- 自动发现（{datetime.now().strftime('%Y-%m-%d')}） ---\n"
                for e in pair_entries[:15]:
                    new_section += e + "\n"
                content = content[:end_pos] + new_section + content[end_pos:]
                f.seek(0)
                f.write(content)
                print(f"  ✅ 已添加 {min(15, len(pair_entries))} 对到 engine.py")

    print(f"  💡 重新运行回测查看新配对效果：python3 run.py pairs backtest")


def list_industries():
    """列出所有行业"""
    industries = get_industries()
    print(f"\n{'='*55}")
    print(f"  📋 行业板块列表 ({len(industries)}个)")
    print(f"{'='*55}")

    # 按关键词高亮用户感兴趣的行业
    highlights = ['医药', '生物', '食品', '饮料', '白酒', '家电', '电子',
                  '计算机', '汽车', '新能源', '银行', '证券', '保险']

    for ind in sorted(industries):
        marker = " ⭐" if any(h in ind for h in highlights) else ""
        print(f"  {ind}{marker}")

    print(f"\n  ⭐ = 你可能感兴趣的行业")
    print(f"\n  💡 扫描: python3 utils/pairs_discovery.py --scan \"行业名称\"")


def main():
    parser = argparse.ArgumentParser(description='配对自动发现系统')
    parser.add_argument('--list-industries', action='store_true', help='列出所有行业')
    parser.add_argument('--scan', default=None, help='扫描指定行业，如"医药生物"')
    parser.add_argument('--scan-all', action='store_true', help='扫描全部行业')
    parser.add_argument('--max-industries', type=int, default=10,
                        help='--scan-all 时最多扫描数(默认10)')
    parser.add_argument('--max-stocks', type=int, default=30,
                        help='每行业最多扫描数(默认30)')
    parser.add_argument('--results', action='store_true', help='查看发现结果')
    parser.add_argument('--add-top', type=int, default=0,
                        help='添加Top N配对到股票池')
    args = parser.parse_args()

    if args.list_industries:
        list_industries()
        return

    if args.results:
        show_results()
        return

    if args.add_top > 0:
        add_top_pairs_to_pool(args.add_top)
        return

    if args.scan:
        scan_industry(args.scan, args.max_stocks)
        return

    if args.scan_all:
        scan_all_industries(args.max_industries)
        return

    # 默认：交互式
    print(f"""
╔═══════════════════════════════════════════════════╗
║     🔍 配对自动发现系统                            ║
║     先扫后跟 — 一次性扫描，自动发现强相关配对       ║
║     最小相关系数: {MIN_CORRELATION}                      ║
║     每行业上限: {MAX_STOCKS_PER_INDUSTRY}只                      ║
╚═══════════════════════════════════════════════════╝
""")

    industries = get_industries()
    if not industries:
        print("  ❌ 无法获取行业列表")
        return

    # 显示用户可能感兴趣的行业
    highlights = ['医药生物', '食品饮料', '白酒', '家电', '电子',
                  '汽车', '计算机', '银行', '证券', '新能源']
    print(f"  推荐扫描的行业:")
    for h in highlights:
        if h in industries:
            print(f"    {h}")
    print(f"\n  全部行业: {len(industries)}个")

    # 交互式：扫描默认行业
    default_industry = '医药生物'
    print(f"\n  ▶ 开始扫描 [{default_industry}]...")
    pairs = scan_industry(default_industry, args.max_stocks)

    if pairs:
        print(f"\n  💡 更多操作:")
        print(f"    python3 utils/pairs_discovery.py --scan \"食品饮料\"")
        print(f"    python3 utils/pairs_discovery.py --scan-all")
        print(f"    python3 utils/pairs_discovery.py --results")
        print(f"    python3 utils/pairs_discovery.py --add-top 20")


if __name__ == '__main__':
    main()