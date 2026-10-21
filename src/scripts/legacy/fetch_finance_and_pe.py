#!/usr/bin/env python3
"""
财务数据 + PE 数据 + 实时价格获取脚本（混合版）
1. 财务数据：Akshare stock_financial_abstract
2. PE 数据：现价 / (Q1_EPS * 4)
3. 实时价格：腾讯财经 API
"""

import akshare as ak
import pandas as pd
import json
import sys
import requests
import random
import time
from datetime import datetime
from pathlib import Path

# === Prism Intent Router 集成 ===
# 意图路由：判断查询类型，优化 API 调用策略
try:
    sys.path.insert(0, str(Path(__file__).parent))
    from prism_router import IntentRouter, RouterConfig
    _PRISM_AVAILABLE = True
except ImportError:
    _PRISM_AVAILABLE = False
    IntentRouter = None
    RouterConfig = None

# === 后端路由 + 多级缓存集成 ===
# 后端 Fallback + 健康探测 + 多级缓存
try:
    from config_loader import load_yaml_config, create_backend_router_from_config, create_multi_level_cache_from_config
    from backend_router import BackendRouter, Backend, FallbackConfig
    from multi_level_cache import MultiLevelCache, DynamicTTL
    _BACKEND_ROUTER_AVAILABLE = True
except ImportError:
    _BACKEND_ROUTER_AVAILABLE = False
    BackendRouter = None
    MultiLevelCache = None
    DynamicTTL = None

# === Speculative RAG 集成 ===
# 双模型加速推理：小模型 draft + 强模型验证
try:
    from speculative_rag import SpeculativeRAG, SpeculativeConfig
    _SPECULATIVE_RAG_AVAILABLE = True
except ImportError:
    _SPECULATIVE_RAG_AVAILABLE = False

# === Retry 优化配置 ===
_RETRY_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # 秒
_RETRY_MAX_DELAY = 16.0  # 秒
_RETRY_JITTER = 1.0      # ±1 秒分散

def _retry_backoff(attempt: int) -> float:
    """计算重试延迟（指数 backoff + jitter）"""
    delay = min(_RETRY_BASE_DELAY * (2 ** attempt), _RETRY_MAX_DELAY)
    jitter = random.uniform(-_RETRY_JITTER, _RETRY_JITTER)
    return max(0.5, delay + jitter)

def _fetch_with_retry(url: str, headers: dict = None, timeout: int = 10) -> requests.Response:
    """带 retry 的 requests.get 封装"""
    last_error = None
    for attempt in range(_RETRY_MAX_RETRIES + 1):
        try:
            return requests.get(url, headers=headers, timeout=timeout)
        except Exception as e:
            last_error = e
            if attempt >= _RETRY_MAX_RETRIES:
                break
            delay = _retry_backoff(attempt)
            print(f"  ⚠️ 请求失败 (attempt {attempt+1}/{_RETRY_MAX_RETRIES}): {e}, 等待 {delay:.1f}s")
            time.sleep(delay)
    raise last_error

# 34 只 A 股配置
STOCKS = {
    'P0-核心': [
        ('恒瑞医药', '600276'),
        ('华东医药', '000963'),
        ('人福医药', '600079'),
        ('科伦药业', '002422'),
        ('药明康德', '603259'),
        ('百利天恒', '688506'),
        ('恩华药业', '002262'),
    ],
    'P1-次核心': [
        ('智飞生物', '300122'),
        ('沃森生物', '300142'),
        ('昊海生科', '688366'),
        ('健民集团', '600976'),
        ('万泰生物', '603392'),
        ('泰格医药', '300347'),
        ('君实生物', '688180'),
        ('康龙化成', '300759'),
        ('贝达药业', '300558'),
        ('复星医药', '600196'),
        ('凯莱英', '002821'),
        ('百济神州', '688235'),
        ('爱美客', '300896'),
    ],
    'P2-扩展': [
        ('片仔癀', '600436'),
        ('白云山', '600332'),
        ('云南白药', '000538'),
        ('鱼跃医疗', '002223'),
        ('以岭药业', '002603'),
        ('海正药业', '600267'),
        ('乐普医疗', '300003'),
        ('九洲药业', '603456'),
        ('华兰生物', '002007'),
        ('博腾股份', '300363'),
        ('同仁堂', '600085'),
        ('上海医药', '601607'),
        ('丽珠集团', '000513'),
        ('奥翔药业', '603229'),
        ('普洛药业', '600216'),
    ],
}


def get_tencent_price(stock_code: str) -> dict:
    """从腾讯财经获取实时价格"""
    try:
        # 判断 A 股类型
        if stock_code.startswith('688') or stock_code.startswith('60'):
            prefix = 'sh'
        elif stock_code.startswith('30') or stock_code.startswith('00'):
            prefix = 'sz'
        else:
            prefix = 'sh'
        
        url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "http://finance.qq.com/",
        }
        
        response = _fetch_with_retry(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            text = response.text
            key = f"v_{prefix}{stock_code}"
            if key in text:
                data_str = text.split(f'{key}="')[1].rstrip('"')
                parts = data_str.split("~")
                
                return {
                    'success': True,
                    'price': float(parts[3]) if parts[3] else None,
                    'open': float(parts[4]) if parts[4] else None,
                    'high': float(parts[32]) if parts[32] else None,
                    'low': float(parts[33]) if parts[33] else None,
                    'volume': float(parts[6]) if parts[6] else None,
                    'amount': float(parts[7]) if parts[7] else None,
                    'change_pct': float(parts[31]) if parts[31] else None,
                    'time': parts[29] if len(parts) > 29 else None,
                }
        
        return {'success': False, 'error': '无数据'}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}


def _clean_value(v):
    """清理同花顺返回的数值字符串，转为 float"""
    if v is False or v is None:
        return 0.0
    if isinstance(v, (int, float)):
        if pd.isna(v):
            return 0.0
        return float(v)
    if isinstance(v, str):
        # 去掉百分号 → 返回百分比数值（如 "23.45%" → 23.45）
        if v.endswith('%'):
            try:
                return float(v[:-1])
            except ValueError:
                return 0.0
        # 去掉亿/万单位 → 返回原始数值（如 "1234.56亿" → 1234.56）
        if v.endswith('亿'):
            try:
                return float(v[:-1])
            except ValueError:
                return 0.0
        if v.endswith('万'):
            try:
                return float(v[:-1]) / 10000.0  # 统一为亿单位
            except ValueError:
                return 0.0
        # 纯数字
        try:
            return float(v)
        except ValueError:
            return 0.0
    return 0.0


def get_financials(symbol: str) -> dict:
    """获取个股财务数据（同花顺接口）"""
    try:
        df = ak.stock_financial_abstract_ths(symbol=symbol)

        if len(df) == 0:
            return {'error': '无数据'}

        row = df.iloc[-1]  # 最新一期财报

        revenue = _clean_value(row.get('营业总收入'))
        profit = _clean_value(row.get('净利润'))
        gross_margin = _clean_value(row.get('销售毛利率'))
        rev_growth = _clean_value(row.get('营业总收入同比增长率'))
        profit_growth = _clean_value(row.get('净利润同比增长率'))
        roe = _clean_value(row.get('净资产收益率'))
        q1_eps = _clean_value(row.get('基本每股收益'))
        report_date = row.get('报告期', '')

        return {
            '财报日期': str(report_date),
            '营收': revenue,       # 单位：亿元
            '利润': profit,        # 单位：亿元
            '毛利率': gross_margin,  # 百分比
            '营收增速': rev_growth,   # 百分比
            '净利增速': profit_growth, # 百分比
            'ROE': roe,            # 百分比
            'Q1_EPS': q1_eps,      # 元
        }

    except Exception as e:
        return {'error': str(e)}


def main():
    """获取财务数据 + PE 数据 + 实时价格并保存"""
    output_dir = Path("/Users/xiashuang/obsidian/all about xia/01-股票投研/data")
    date_str = datetime.now().strftime("%Y%m%d")
    
    # === Prism Router 初始化 ===
    if _PRISM_AVAILABLE:
        router = IntentRouter(RouterConfig(
            simple_keywords=["价格", "股价", "实时价", "涨跌幅", "PE", "市盈率"],
            complex_keywords=["财务", "分析", "对比", "趋势", "原因", "为什么", "机制"],
            enable_cache=True,
            fallback_to_llm=True,
        ))
        print("🔀 Prism Router 已加载")
    else:
        router = None
        print("⚠️ Prism Router 未加载（prism_router.py 不存在）")
    
    # === Speculative RAG 初始化 ===
    if _SPECULATIVE_RAG_AVAILABLE:
        speculative_rag = SpeculativeRAG(SpeculativeConfig(
            draft_model="sensenova-6.7-flash-lite",
            verify_model="deepseek-v4-flash",
            quality_threshold=0.7,
            enable_cache=True,
        ))
        print("🚀 Speculative RAG 已加载 (draft: sensenova-6.7-flash-lite, verify: deepseek-v4-flash)")
    else:
        speculative_rag = None
        print("⚠️ Speculative RAG 未加载（speculative_rag.py 不存在或 openai 库缺失）")
    
    print("="*60)
    print("财务数据 + PE 数据 + 实时价格获取（混合版）")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    finance_results = []
    pe_data = {}
    price_data = {}
    failed = []
    
    for priority, stock_list in STOCKS.items():
        print(f"\n【{priority}】")
        for name, code in stock_list:
            # === Prism Router: 记录查询意图 ===
            if router:
                query = f"{name} 财务数据 + 实时价格"
                result = router.classify(query)
                # 简单查询 → 优先走缓存/轻量 API
                # 复杂查询 → 走完整财务分析
                intent_tag = f"[{result.intent.value[:4]}]"
            else:
                intent_tag = ""
            
            # 获取财务数据
            fin = get_financials(code)
            if 'error' in fin:
                print(f"  ✗ {intent_tag} {name}({code}): 财务数据获取失败")
                failed.append(code)
                finance_results.append({
                    '优先级': priority,
                    '股票': name,
                    '代码': code,
                    '状态': '✗ 数据获取失败',
                    '错误': fin['error'],
                })
                continue
            
            # 获取实时价格
            price = get_tencent_price(code)
            if not price.get('success'):
                print(f"  ⚠️ {intent_tag} {name}({code}): 实时价格获取失败 ({price.get('error')})")
                price_data[code] = None
            else:
                print(f"  ✓ {intent_tag} {name}({code}): 实时价={price['price']}, 涨跌幅={price['change_pct']}%")
                price_data[code] = price
            
            # 计算 PE
            q1_eps = fin.get('Q1_EPS', 0)
            pe_ttm = None
            if q1_eps and q1_eps > 0:
                pe_ttm = round(price['price'] / (q1_eps * 4), 1) if price.get('price') else None
            
            # 同花顺数据已经是亿元单位，直接使用
            revenue = fin['营收'] if fin['营收'] else 0
            profit = fin['利润'] if fin['利润'] else 0
            gross_margin = fin['毛利率'] if fin['毛利率'] else 0
            rev_growth = fin['营收增速'] if fin['营收增速'] else 0
            profit_growth = fin['净利增速'] if fin['净利增速'] else 0
            roe = fin['ROE'] if fin['ROE'] else 0
            
            # 增长状态判断
            if rev_growth > 10 and profit_growth > 10:
                status = '✓ 双增长'
            elif rev_growth > 0 and profit_growth > 0:
                status = '✓ 增长'
            elif rev_growth < -10 or profit_growth < -10:
                status = '⚠ 双降'
            else:
                status = '○ 持平'
            
            finance_results.append({
                '优先级': priority,
                '股票': name,
                '代码': code,
                '状态': status,
                '财报日期': fin['财报日期'],
                '营收(亿)': round(revenue, 2),
                '营收增速(%)': round(rev_growth, 2),
                '利润(亿)': round(profit, 2),
                '利润增速(%)': round(profit_growth, 2),
                '毛利率(%)': round(gross_margin, 2),
                'ROE(%)': round(roe, 2),
                '实时价': price.get('price') if price else None,
                '涨跌幅(%)': price.get('change_pct') if price else None,
                'PE_TTM': pe_ttm,
                '错误': '',
            })
            
            if pe_ttm is not None:
                pe_data[code] = pe_ttm
    
    # ⚠️ 文件名冲突 bug（2026-10-14 复核确认，纯注释未改逻辑；运行副本在
    # ~/.hermes/Scripts/fetch_finance_and_pe.py，两份同此说明）：
    # 本脚本把"财报 schema"CSV 写进与 investment_pipeline.py 相同的
    # `每日股票检查_{date}.csv`，谁后跑谁覆盖。2026-09-24 本脚本 09:56 先写入
    # 占用文件名、pipeline 当日未再产出，当日行情缺失；已回填
    # `每日股票检查_20260924_backfill.csv`（收盘口径，原件未动）。
    # 修复建议：输出改名 `财务摘要_{date_str}.csv`（改动前需确认无脚本按旧名读财报）。
    # 保存财务数据 CSV
    df_finance = pd.DataFrame(finance_results)
    csv_path = output_dir / "daily_check" / f"每日股票检查_{date_str}.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df_finance.to_csv(csv_path, index=False, encoding='utf-8-sig')
    
    # 保存财务数据 Markdown
    md_path = output_dir / "daily_check" / f"每日数据完整性检查_{date_str}.md"
    md_content = generate_finance_report(finance_results, date_str)
    md_path.write_text(md_content, encoding='utf-8')
    
    # 保存 PE 数据 JSON
    pe_output = {
        'date': date_str,
        'source': 'Akshare stock_financial_abstract + 腾讯财经 API',
        'method': 'PE_TTM = 现价 / (Q1_EPS * 4)',
        'success_rate': f"{len(pe_data)}/34 ({len(pe_data)/34*100:.1f}%)",
        'pe_data': pe_data,
        'failed': failed,
    }
    pe_path = output_dir / f"pe_data_{date_str}.json"
    pe_path.write_text(json.dumps(pe_output, ensure_ascii=False, indent=2), encoding='utf-8')
    
    # 保存实时价格 JSON
    price_output = {
        'date': date_str,
        'source': '腾讯财经 API (qt.gtimg.cn)',
        'price_data': price_data,
    }
    price_path = output_dir / f"price_data_{date_str}.json"
    price_path.write_text(json.dumps(price_output, ensure_ascii=False, indent=2), encoding='utf-8')
    
    # 统计
    success = len([r for r in finance_results if r['状态'] != '✗ 数据获取失败'])
    double_growth = [r for r in finance_results if r['状态'] == '✓ 双增长']
    double_decline = [r for r in finance_results if r['状态'] == '⚠ 双降']
    
    print(f"\n{'='*60}")
    print(f"✓ 财务数据 CSV: {csv_path}")
    print(f"✓ 财务数据 Markdown: {md_path}")
    print(f"✓ PE 数据 JSON: {pe_path}")
    print(f"✓ 实时价格 JSON: {price_path}")
    print(f"✓ 获取率: {len(pe_data)}/34 ({len(pe_data)/34*100:.1f}%)")
    print(f"✓ 成功: {success}/34, 双增长: {len(double_growth)}, 双降: {len(double_decline)}")
    
    # === Prism Router 统计输出 ===
    if router:
        stats = router.get_stats()
        print(f"\n🔀 Prism Router 统计:")
        print(f"   总查询: {stats['total']}")
        print(f"   简单检索: {stats['simple_search']} ({stats['simple_ratio']})")
        print(f"   复杂推理: {stats['complex_reasoning']}")
        print(f"   预期延迟节省: {stats['estimated_latency_saved_pct']}")
    
    # === Speculative RAG 统计输出 ===
    if speculative_rag:
        stats = speculative_rag.get_stats()
        print(f"\n🚀 Speculative RAG 统计:")
        print(f"   总查询: {stats['total']}")
        print(f"   Draft 接受: {stats['draft_accepted']}")
        print(f"   Draft 拒绝: {stats['draft_rejected']}")
        print(f"   重新生成: {stats['regenerated']}")
        if stats.get('draft_accepted', 0) > 0:
            print(f"   预估时间节省: {stats.get('estimated_time_saved_ms', 0)}ms")
            print(f"   预估 Token 节省: {stats.get('estimated_token_saved', 0)}")
        print(f"   缓存大小: {stats['cache_size']}")
    
    print(f"{'='*60}")
    
    return 0 if len(pe_data) >= 30 else 1


def generate_finance_report(results, date_str):
    """生成财务数据 Markdown 报告"""
    report = f"""# 每日财务数据检查 - {date_str}

**检查时间：** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**检查股票：** {len(results)} 只
**成功：** {len([r for r in results if r['状态'] != '✗ 数据获取失败'])} 只
**失败：** {len([r for r in results if r['状态'] == '✗ 数据获取失败'])} 只

---

## 财务数据汇总

| 股票 | 代码 | 状态 | 营收(亿) | 营收增速 | 利润(亿) | 利润增速 | 毛利率 | ROE | 实时价 | 涨跌幅 | PE_TTM |
|------|------|------|---------|---------|---------|---------|--------|-----|--------|--------|--------|
"""
    
    for priority in STOCKS.keys():
        priority_results = [r for r in results if r.get('优先级') == priority]
        if not priority_results:
            continue
        
        for r in priority_results:
            if r['状态'] == '✗ 数据获取失败':
                report += f"| {r['股票']} | {r['代码']} | {r['状态']} | - | - | - | - | - | - | - | - | - |\n"
            else:
                report += f"| {r['股票']} | {r['代码']} | {r['状态']} | {r['营收(亿)']} | {r['营收增速(%)']:+.1f}% | {r['利润(亿)']} | {r['利润增速(%)']:+.1f}% | {r['毛利率(%)']}% | {r['ROE(%)']}% | {r.get('实时价', 'N/A')} | {r.get('涨跌幅(%)', 'N/A')}% | {r.get('PE_TTM', 'N/A')} |\n"
        report += "\n"
    
    # 重点提示
    double_growth = [r for r in results if r['状态'] == '✓ 双增长']
    double_decline = [r for r in results if r['状态'] == '⚠ 双降']
    
    if double_growth:
        report += "## 📈 营收利润双增长（>10%）\n\n"
        for r in double_growth:
            report += f"- {r['股票']}({r['代码']}): 营收 {r['营收增速(%)']:+.1f}%, 利润 {r['利润增速(%)']:+.1f}%\n"
        report += "\n"
    
    if double_decline:
        report += "## 📉 营收利润双降（<-10%）\n\n"
        for r in double_decline:
            report += f"- {r['股票']}({r['代码']}): 营收 {r['营收增速(%)']:+.1f}%, 利润 {r['利润增速(%)']:+.1f}%\n"
        report += "\n"
    
    report += f"*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n"
    
    return report


if __name__ == "__main__":
    sys.exit(main())
