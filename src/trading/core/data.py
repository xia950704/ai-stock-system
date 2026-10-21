"""
数据模块：从东方财富API获取A股实时数据
支持个股日K线下载 + 技术指标计算
"""
import numpy as np
import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import time

# ==================== 股票池 ====================
# 精选流动性好的A股（不同行业、不同风格）
STOCK_POOL = {
    '000858': '五粮液',   # 消费/白酒
    '000333': '美的集团',  # 家电
    '600519': '贵州茅台',  # 白酒
    '000002': '万科A',     # 地产
    '601012': '隆基绿能',  # 光伏
    '300750': '宁德时代',  # 新能源
    '600036': '招商银行',  # 银行
    '000725': '京东方A',   # 面板
    '002415': '海康威视',  # 安防
    '600030': '中信证券',  # 券商
    # ========== 医药股（来自自定义监控池） ==========
    # P0 核心医药
    '600276': '恒瑞医药',   # 创新药龙头
    '000963': '华东医药',  # 医药综合
    '600079': '人福医药',  # 麻醉镇痛
    '002422': '科伦药业',  # 大输液+创新药
    '603259': '药明康德',  # CXO龙头
    '688506': '百利天恒',  # 双抗ADC
    # P1 次核心医药
    '300122': '智飞生物',  # 疫苗
    '300142': '沃森生物',  # 疫苗
    '688366': '昊海生科',  # 医美/眼科
    '600976': '健民集团',  # 中药
    '603392': '万泰生物',  # 疫苗/诊断
    '300347': '泰格医药',  # CXO临床
    '688180': '君实生物',  # 创新药PD-1
    '300759': '康龙化成',  # CXO全流程
    '300558': '贝达药业',  # 创新药
    '600196': '复星医药',  # 综合医药
    '002821': '凯莱英',    # CDMO
    '688235': '百济神州',  # 创新药国际化
    '300896': '爱美客',    # 医美
    # P2 扩展医药
    '600436': '片仔癀',    # 中药
    '600332': '白云山',    # 中药/饮料
    '000538': '云南白药',  # 中药/消费品
    '002223': '鱼跃医疗',  # 医疗器械
    '002603': '以岭药业',  # 中药
    '600267': '海正药业',  # 原料药
    '300003': '乐普医疗',  # 医疗器械
    '603456': '九洲药业',  # CDMO
    '002007': '华兰生物',  # 血制品
    '300363': '博腾股份',  # CDMO
    '600085': '同仁堂',    # 中药
    '601607': '上海医药',  # 医药商业
    '000513': '丽珠集团',  # 综合医药
    '603229': '奥翔药业',  # 原料药
    '600216': '普洛药业',  # 原料药/CDMO
    '002262': '恩华药业',  # 麻醉神经
    # ========== 配对套利补充股 ==========
    '000651': '格力电器',  # 家电（配美的）
    '002236': '大华股份',  # 安防（配海康）
    # ========== 自动发现配对（2026-07-16） ==========
    '000596': '古井贡酒',   # 白酒
    '000860': '顺鑫农业',   # 白酒
    '002304': '洋河股份',   # 白酒
    '600197': '伊力特',     # 白酒
    '600559': '老白干酒',   # 白酒
    '600779': '水井坊',     # 白酒
    '603589': '口子窖',     # 白酒
    # ========== 自动发现配对（2026-07-16）第二批 ==========
    # ========== 自动发现配对（2026-07-16）第二批 ==========
    '002045': '国光电器',
    '002351': '漫步者',
    '002709': '天赐材料',
    '002812': '恩捷股份',
    '300676': '华大基因',
    '300760': '迈瑞医疗',
    '300783': '三只松鼠',
    '600015': '华夏银行',
    '600016': '民生银行',
    '600118': '中国卫星',
    '600420': '国药现代',
    '600422': '昆药集团',
    '600584': '长电科技',
    '600587': '新华医疗',
    '600809': '山西汾酒',
    '601106': '中国一重',
    '601166': '兴业银行',
    '601169': '北京银行',
    '601788': '光大证券',
    '601818': '光大银行',
    '601901': '方正证券',
    '603127': '昭衍新药',
    '603369': '今世缘',
    '603658': '安图生物',
    '603659': '璞泰来',
    '603719': '良品铺子',
    '603882': '金域医学',
    '603986': '兆易创新',
    '688008': '澜起科技',
    '688041': '海光信息',
    '688202': '美迪西',
    '688236': '春立医疗',
    '688276': '百克生物',

}

# 市场代码映射
MARKET_MAP = {'6': '1', '0': '0', '3': '0'}  # 6xx→上海, 0xx/3xx→深圳

def get_secid(symbol):
    """获取东方财富的secid格式"""
    prefix = '1' if symbol.startswith('6') else '0'
    return f"{prefix}.{symbol}"

def fetch_a_stock_data(symbol, start_date='20250101', end_date=None):
    """
    从新浪财经API获取A股日K线
    symbol: 股票代码，如 '000858'
    返回: DataFrame with columns [开盘, 收盘, 最高, 最低, 成交量]
    """
    market = 'sh' if symbol.startswith('6') else 'sz'
    url = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': f'https://finance.sina.com.cn/realstock/company/{market}{symbol}/nc.shtml'
    }

    params = {"symbol": f"{market}{symbol}", "scale": "240", "datalen": "800"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=15)
        data = r.json()

        if not isinstance(data, list) or len(data) == 0:
            print(f"⚠️ {symbol} 数据为空")
            return None

        rows = []
        for item in data:
            rows.append({
                '日期': item.get('day', ''),
                '开盘': float(item.get('open', 0)),
                '收盘': float(item.get('close', 0)),
                '最高': float(item.get('high', 0)),
                '最低': float(item.get('low', 0)),
                '成交量': int(float(item.get('volume', 0))),
            })

        df = pd.DataFrame(rows)
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.set_index('日期')
        df = df.sort_index()

        # 按日期过滤
        if start_date:
            df = df[df.index >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df.index <= pd.to_datetime(end_date)]

        return df

    except Exception as e:
        print(f"❌ {symbol} 数据获取失败: {e}")
        return None

def fetch_multiple_stocks(symbols=None, start_date='20250101', end_date=None):
    """
    批量获取多只股票数据
    返回 {symbol: DataFrame} 字典
    """
    if symbols is None:
        symbols = list(STOCK_POOL.keys())

    results = {}
    for i, symbol in enumerate(symbols):
        name = STOCK_POOL.get(symbol, symbol)
        print(f"  [{i+1}/{len(symbols)}] 获取 {symbol} ({name})...", end=' ')
        df = fetch_a_stock_data(symbol, start_date, end_date)
        if df is not None and len(df) > 20:
            results[symbol] = df
            price = df['收盘'].iloc[-1]
            print(f"✅ {len(df)}天, 最新¥{price:.2f}")
        else:
            print(f"❌ 数据不足")
        time.sleep(0.3)  # API限流保护

    return results

def add_technical_features(df):
    """添加技术指标特征"""
    df = df.copy()

    # 移动平均线
    df['MA5'] = df['收盘'].rolling(5).mean()
    df['MA10'] = df['收盘'].rolling(10).mean()
    df['MA20'] = df['收盘'].rolling(20).mean()
    df['MA60'] = df['收盘'].rolling(60).mean()

    # 价格与均线偏离
    df['Pct_MA5'] = (df['收盘'] - df['MA5']) / df['MA5']
    df['Pct_MA10'] = (df['收盘'] - df['MA10']) / df['MA10']
    df['Pct_MA20'] = (df['收盘'] - df['MA20']) / df['MA20']

    # RSI
    delta = df['收盘'].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # 收益率
    df['Return_1d'] = df['收盘'].pct_change(1)
    df['Return_5d'] = df['收盘'].pct_change(5)
    df['Return_10d'] = df['收盘'].pct_change(10)
    df['Return_20d'] = df['收盘'].pct_change(20)

    # 波动率
    df['Volatility_5d'] = df['Return_1d'].rolling(5).std()
    df['Volatility_10d'] = df['Return_1d'].rolling(10).std()

    # 成交量变化
    df['Volume_MA5'] = df['成交量'].rolling(5).mean()
    df['Volume_MA20'] = df['成交量'].rolling(20).mean()
    df['Volume_Ratio'] = df['成交量'] / df['Volume_MA5']

    # MACD
    ema12 = df['收盘'].ewm(span=12).mean()
    ema26 = df['收盘'].ewm(span=26).mean()
    df['MACD'] = ema12 - ema26
    df['MACD_Signal'] = df['MACD'].ewm(span=9).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']

    # 布林带
    df['BB_Mid'] = df['收盘'].rolling(20).mean()
    bb_std = df['收盘'].rolling(20).std()
    df['BB_Upper'] = df['BB_Mid'] + 2 * bb_std
    df['BB_Lower'] = df['BB_Mid'] - 2 * bb_std
    df['BB_Position'] = (df['收盘'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])

    # 价格位置
    df['Price_High_20d'] = df['收盘'].rolling(20).max()
    df['Price_Low_20d'] = df['收盘'].rolling(20).min()
    df['Price_Position'] = (df['收盘'] - df['Price_Low_20d']) / (df['Price_High_20d'] - df['Price_Low_20d'])

    return df.dropna()

def prepare_ml_data(df):
    """准备ML训练数据"""
    df = add_technical_features(df).copy()

    feature_cols = [
        'Pct_MA5', 'Pct_MA10', 'Pct_MA20',
        'RSI',
        'Return_1d', 'Return_5d', 'Return_10d',
        'Volatility_5d', 'Volatility_10d',
        'Volume_Ratio',
        'MACD', 'MACD_Hist',
        'BB_Position', 'Price_Position'
    ]

    # 只保留存在的特征
    feature_cols = [c for c in feature_cols if c in df.columns]

    # 标签：未来1天涨(1)跌(0)
    df['Target'] = (df['收盘'].shift(-1) > df['收盘']).astype(int)

    return df[feature_cols], df['Target'], df

def list_available_stocks():
    """列出可用的股票池"""
    print(f"\n{'='*50}")
    print(f"  📋 A股股票池 ({len(STOCK_POOL)}只)")
    print(f"{'='*50}")
    for code, name in STOCK_POOL.items():
        market = "深圳" if code.startswith('0') or code.startswith('3') else "上海"
        print(f"  {code} ({name}) [{market}]")
    print(f"{'='*50}")
    print(f"  使用: python3 run_pipeline.py --symbol 000858")
    print(f"{'='*50}")

if __name__ == '__main__':
    # 测试：获取五粮液数据
    df = fetch_a_stock_data('000858')
    if df is not None:
        print(f"\n✅ 获取成功: {len(df)} 条日K线")
        print(df.tail())
        X, y, df_full = prepare_ml_data(df)
        print(f"\n特征维度: {X.shape}")
        print(f"特征列表: {list(X.columns)}")
        print(f"涨跌分布: 涨={y.sum()} 跌={(1-y).sum()}")
