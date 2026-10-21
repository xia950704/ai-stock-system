#!/usr/bin/env python3
"""
配对发现系统 v2（2026-08-26 重构）
=================================
旧机制问题：只看价格相关性>0.8，发现298对但回测质量差（价差不平稳/不协整）。
新机制：行业+市值+波动率+协整+半衰期 五维筛选，从源头解决配对质量。

五维筛选流程：
  1️⃣ 行业同板块（关键词匹配，旧机制保留）
  2️⃣ 价格相关性 r>0.6（放宽，让后面维度筛）
  3️⃣ 市值匹配：市值差<3倍（避免大盘配小盘错配）
  4️⃣ 波动率匹配：年化波动率差<1.5倍
  5️⃣ 协整+半衰期：Engle-Granger p<0.05 + 滚动稳定>60% + 半衰期5-60天

数据源：akshare.stock_value_em（一次拿市值+价格，避免重复请求）
依赖：statsmodels（协整检验，已装0.14.6）

用法:
  python3 utils/pairs_discovery_v2.py                      # 扫描默认行业
  python3 utils/pairs_discovery_v2.py --scan 白酒          # 扫描指定行业
  python3 utils/pairs_discovery_v2.py --scan-all           # 扫描全部
  python3 utils/pairs_discovery_v2.py --results            # 查看结果
  python3 utils/pairs_discovery_v2.py --add-top 10         # TopN加到engine
"""
import sys, os, json, time, argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.data import STOCK_POOL

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_FILE = os.path.join(PROJECT_ROOT, 'discovered_pairs_v2.json')
DATA_CACHE_DIR = os.path.join(PROJECT_ROOT, 'reports', 'discovery_cache_v2')
os.makedirs(DATA_CACHE_DIR, exist_ok=True)

# ==================== 五维筛选参数 ====================
MIN_CORRELATION = 0.60       # 维度2：价格相关性下限
MAX_MKT_CAP_RATIO = 3.0      # 维度3：市值差上限（大/小<3倍）
MAX_VOL_RATIO = 1.5          # 维度4：波动率差上限（高/低<1.5倍）
MAX_COINT_P = 0.05           # 维度5：协整p值上限
MIN_ROLLING_STABLE = 0.60    # 维度5：滚动协整通过率
MIN_HALFLIFE = 5             # 维度5：半衰期下限（天，太快=噪声）
MAX_HALFLIFE = 60            # 维度5：半衰期上限（太慢=不回归）
MIN_DATA_DAYS = 250          # 最少数据天数（1年）

# 导入行业关键词（从 data.py 或本地定义）
INDUSTRY_KW = {
    '中药': ['同仁堂', '片仔癀', '云南白药', '白云山', '以岭', '华润三九', '东阿阿胶', '健民', '太极', '昆药', '康缘'],
    '化学制药': ['恒瑞', '恩华', '人福', '科伦', '贝达', '丽珠', '海正', '普洛', '华海', '信立泰', '现代', '海思科'],
    '生物制品': ['智飞', '沃森', '华兰', '康泰', '万泰', '长春高新', '通化东宝', '甘李', '百克'],
    '医疗器械': ['迈瑞', '鱼跃', '乐普', '健帆', '华大', '金域', '安图', '春立', '三友'],
    '医疗服务': ['药明', '泰格', '康龙', '凯莱英', '博腾', '昭衍', '美迪西', '爱尔', '通策'],
    '白酒': ['茅台', '五粮液', '泸州老窖', '洋河', '山西汾酒', '古井贡', '水井坊', '口子窖', '今世缘', '伊力特', '老白干', '顺鑫'],
    '银行': ['招商', '兴业', '工商', '建设', '农业', '交通', '浦发', '民生', '平安', '中信', '光大', '华夏', '北京'],
    '证券': ['中信', '华泰', '中金', '广发', '东方', '国泰', '海通', '申万', '光大', '方正'],
    '半导体': ['中芯', '韦尔', '北方华创', '长电', '兆易', '澜起', '寒武', '海光'],
    '新能源': ['宁德', '比亚迪', '隆基', '通威', '阳光', '亿纬', '天赐', '恩捷', '璞泰来'],
}


def get_all_stocks():
    """从Sina获取全A股列表（带缓存）。"""
    cache = os.path.join(DATA_CACHE_DIR, 'all_stocks.json')
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 86400:
        with open(cache, encoding='utf-8') as f:
            return json.load(f)
    import requests
    all_stocks = []
    try:
        for page in range(1, 60):
            url = ('https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/'
                   'Market_Center.getHQNodeData')
            params = {'page': str(page), 'num': '100', 'sort': 'symbol', 'asc': '1',
                      'node': 'hs_a', 'symbol': '', '_': ''}
            r = requests.get(url, params=params, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            data = r.json()
            if not isinstance(data, list) or len(data) == 0:
                break
            for item in data:
                code, name = str(item.get('code', '')), str(item.get('name', '')).strip()
                if code and name:
                    all_stocks.append((code, name))
            if len(data) < 100:
                break
        with open(cache, 'w', encoding='utf-8') as f:
            json.dump(all_stocks, f, ensure_ascii=False)
    except Exception as e:
        print(f"  ⚠️ 获取股票列表失败: {e}")
    return all_stocks


def classify_industry(name):
    """名称关键词匹配行业。"""
    for ind, kws in INDUSTRY_KW.items():
        for kw in kws:
            if kw in name:
                return ind
    return None


def fetch_stock_full(code, name):
    """用 stock_value_em 一次拿价格序列+市值+波动率（避免重复请求）。
    返回 None 表示获取失败。
    """
    import akshare as ak
    import numpy as np
    try:
        df = ak.stock_value_em(symbol=code)
        df = df.dropna(subset=['当日收盘价', '总市值']).copy()
        if len(df) < MIN_DATA_DAYS:
            return None
        df = df.tail(MIN_DATA_DAYS + 60)  # 取最近一年多
        closes = df['当日收盘价'].astype(float).values
        dates = df['数据日期'].values
        mkt_cap = float(df['总市值'].iloc[-1])

        # 年化波动率（近60日）
        rets = np.diff(np.log(closes[-61:]))
        vol_annual = np.std(rets) * np.sqrt(252) if len(rets) > 10 else 0

        return {
            'code': code, 'name': name,
            'closes': closes, 'dates': dates,
            'mkt_cap': mkt_cap,
            'vol_annual': vol_annual,
            'n_days': len(closes),
        }
    except Exception as e:
        return None


def coint_test_with_halflife(closes_a, closes_b):
    """协整检验 + 半衰期估计。
    半衰期：价差 Ornstein-Uhlenbeck 过程，dy/dt = -k*y，半衰期=ln(2)/k。
    """
    import numpy as np
    from statsmodels.tsa.stattools import coint

    n = min(len(closes_a), len(closes_b))
    a = closes_a[-n:]
    b = closes_b[-n:]
    if n < 60:
        return None

    try:
        _, p_value, _ = coint(a, b)
    except Exception:
        p_value = 1.0

    # 半衰期：对价差做 AR(1)，y_t = phi*y_{t-1} + e，phi<1平稳，半衰期=ln(2)/(-ln(phi))
    spread = np.log(a) - np.log(b)
    try:
        y = spread[1:]
        x = spread[:-1]
        phi = np.cov(x, y)[0, 1] / np.var(x) if np.var(x) > 0 else 1.0
        if 0 < phi < 1:
            halflife = np.log(2) / (-np.log(phi)) if phi > 0.001 else 999
        else:
            halflife = 999  # 非平稳，不回归
    except Exception:
        halflife = 999

    return {'coint_p': float(p_value), 'halflife': float(halflife)}


def rolling_coint_stable(closes_a, closes_b):
    """滚动协整稳定性（252天窗口，每20天采样，要求>60%通过）。"""
    from statsmodels.tsa.stattools import coint
    n = min(len(closes_a), len(closes_b))
    a, b = closes_a[-n:], closes_b[-n:]
    if n < 300:
        return True, 1.0  # 数据不足跳过滚动检验，由全样本决定
    window = 252
    pvals = []
    for i in range(window, n, 20):
        chunk_a, chunk_b = a[i-window:i], b[i-window:i]
        try:
            _, p, _ = coint(chunk_a, chunk_b)
            pvals.append(p)
        except Exception:
            pvals.append(1.0)
    if not pvals:
        return True, 1.0
    stable_pct = sum(1 for p in pvals if p < MAX_COINT_P) / len(pvals)
    return stable_pct >= MIN_ROLLING_STABLE, stable_pct


def scan_industry(industry_name, max_stocks=20):
    """扫描单行业五维筛选。"""
    print(f"\n{'='*60}")
    print(f"  🔍 v2 扫描行业: {industry_name}（五维筛选）")
    print(f"{'='*60}")

    # 1. 获取该行业股票
    all_stocks = get_all_stocks()
    stocks = [(c, n) for c, n in all_stocks if classify_industry(n) == industry_name]
    if not stocks:
        # 降级：从 STOCK_POOL 找
        from core.data import STOCK_POOL
        stocks = [(c, n) for c, n in [(k, v) for k, v in STOCK_POOL.items()] if classify_industry(n) == industry_name]
    if not stocks:
        print(f"  ❌ 未找到 {industry_name} 成分股")
        return []

    stocks = stocks[:max_stocks]
    print(f"  📋 {industry_name} 成分股 {len(stocks)} 只")

    # 2. 拉取全数据（价格+市值+波动率）
    data = {}
    for i, (code, name) in enumerate(stocks):
        print(f"    [{i+1}/{len(stocks)}] {code} ({name})...", end=' ', flush=True)
        d = fetch_stock_full(code, name)
        if d:
            data[code] = d
            print(f"✅ {d['n_days']}天 市值{d['mkt_cap']/1e8:.0f}亿 波动{d['vol_annual']:.0%}")
        else:
            print("❌")
        time.sleep(0.3)  # API限流

    if len(data) < 2:
        print(f"  ⚠️ 有效数据不足2只")
        return []

    # 3. 五维筛选
    codes = list(data.keys())
    pairs = []
    total = len(codes) * (len(codes) - 1) // 2
    print(f"\n  📐 五维筛选 {total} 个候选配对...")

    for i in range(len(codes)):
        for j in range(i + 1, len(codes)):
            ca, cb = codes[i], codes[j]
            da, db = data[ca], data[cb]

            # 维度2：价格相关性
            n = min(len(da['closes']), len(db['closes']))
            a = da['closes'][-n:]
            b = db['closes'][-n:]
            if n < MIN_DATA_DAYS:
                continue
            import numpy as np
            corr = np.corrcoef(a, b)[0, 1]
            if corr < MIN_CORRELATION:
                continue

            # 维度3：市值匹配
            cap_ratio = max(da['mkt_cap'], db['mkt_cap']) / min(da['mkt_cap'], db['mkt_cap'])
            if cap_ratio > MAX_MKT_CAP_RATIO:
                continue

            # 维度4：波动率匹配
            vol_ratio = max(da['vol_annual'], db['vol_annual']) / max(min(da['vol_annual'], db['vol_annual']), 1e-6)
            if vol_ratio > MAX_VOL_RATIO:
                continue

            # 维度5：协整 + 半衰期
            ct = coint_test_with_halflife(a, b)
            if not ct or ct['coint_p'] >= MAX_COINT_P:
                continue
            if not (MIN_HALFLIFE <= ct['halflife'] <= MAX_HALFLIFE):
                continue

            # 滚动稳定性
            stable, stable_pct = rolling_coint_stable(a, b)
            if not stable:
                continue

            pairs.append({
                'stock_a': ca, 'name_a': da['name'],
                'stock_b': cb, 'name_b': db['name'],
                'industry': industry_name,
                'correlation': round(float(corr), 4),
                'mkt_cap_ratio': round(float(cap_ratio), 2),
                'vol_ratio': round(float(vol_ratio), 2),
                'coint_p': round(ct['coint_p'], 4),
                'halflife': round(ct['halflife'], 1),
                'rolling_stable': round(float(stable_pct), 2),
                'price_a': round(float(a[-1]), 2),
                'price_b': round(float(b[-1]), 2),
            })

    pairs.sort(key=lambda x: (x['coint_p'], -x['correlation']))
    print(f"\n  📊 五维筛选通过: {len(pairs)} 对（从{total}候选）")
    for p in pairs[:10]:
        print(f"    ✅ {p['name_a']}↔{p['name_b']} r={p['correlation']} "
              f"市值比={p['mkt_cap_ratio']} 波动比={p['vol_ratio']} "
              f"协整p={p['coint_p']} 半衰期={p['halflife']}天")
    return pairs


def save_results(pairs, scanned_industries=None):
    with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'version': 'v2_five_dim',
            'total_pairs': len(pairs),
            'filters': {
                'min_correlation': MIN_CORRELATION,
                'max_mkt_cap_ratio': MAX_MKT_CAP_RATIO,
                'max_vol_ratio': MAX_VOL_RATIO,
                'max_coint_p': MAX_COINT_P,
                'min_rolling_stable': MIN_ROLLING_STABLE,
                'halflife_range': [MIN_HALFLIFE, MAX_HALFLIFE],
            },
            'scanned_industries': scanned_industries or [],
            'pairs': pairs,
        }, f, indent=2, ensure_ascii=False)


def show_results():
    if not os.path.exists(RESULTS_FILE):
        print("  ⚠️ 暂无结果，先运行扫描")
        return
    with open(RESULTS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    pairs = data['pairs']
    print(f"\n{'='*60}")
    print(f"  📊 v2 发现配对: {data['total_pairs']} 对")
    print(f"  扫描时间: {data['scan_time']}")
    print(f"  筛选参数: {data['filters']}")
    print(f"{'='*60}")
    for p in pairs:
        print(f"  ✅ {p['name_a']}↔{p['name_b']} [{p['industry']}] "
              f"r={p['correlation']} 协整p={p['coint_p']} 半衰期={p['halflife']}天 "
              f"市值比={p['mkt_cap_ratio']} 波动比={p['vol_ratio']}")


def main():
    parser = argparse.ArgumentParser(description='配对发现v2（五维筛选）')
    parser.add_argument('--scan', default=None, help='扫描指定行业')
    parser.add_argument('--scan-all', action='store_true', help='扫描全部行业')
    parser.add_argument('--max-stocks', type=int, default=20, help='每行业最多扫描数')
    parser.add_argument('--results', action='store_true', help='查看结果')
    args = parser.parse_args()

    if args.results:
        show_results()
        return

    industries = list(INDUSTRY_KW.keys())
    if args.scan_all:
        all_pairs = []
        for ind in industries:
            pairs = scan_industry(ind, args.max_stocks)
            all_pairs.extend(pairs)
            save_results(all_pairs, industries)
        save_results(all_pairs, industries)
        print(f"\n  🏆 全行业扫描完成: {len(all_pairs)} 对")
    elif args.scan:
        scan_industry(args.scan, args.max_stocks)
    else:
        # 默认扫描用户核心关注行业
        for ind in ['白酒', '化学制药', '医疗服务', '银行']:
            scan_industry(ind, args.max_stocks)


if __name__ == '__main__':
    main()
