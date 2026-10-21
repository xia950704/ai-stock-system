#!/usr/bin/env python3
"""
股票价格预警系统 — 71只监控股票
===================================
1. 从腾讯行情接口拉取实时价格（A股+港股）
2. 比对买入/卖出区间
3. 生成预警消息
4. 通过 iMessage 推送

用法：
    python stock_price_alert.py [--dry-run] [--verbose]
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from contextlib import redirect_stdout, nullcontext
from collections import defaultdict
from pathlib import Path

# ============================================================
# 配置
# ============================================================
WORKSPACE = os.environ.get(
    "HERMES_WORKSPACE",
    os.path.expanduser("~/harness/stock_daily"),
)
PORTFOLIO_JSON = os.path.join(WORKSPACE, "stock_portfolio_enriched.json")
ALERT_LOG = os.path.join(WORKSPACE, "stock_daily", "alert_log.jsonl")
TODAY = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
PRICE_JSON = os.path.join(WORKSPACE, "stock_daily", f"stock_prices_{TODAY}.json")

# 腾讯行情接口
TENCENT_URL = "https://qt.gtimg.cn/q="

# 预警阈值
BUY_ZONE_WARNING = 0.05    # 距离买入区间 < 5% 时提醒
SELL_ZONE_WARNING = 0.05   # 距离卖出区间 < 5% 时提醒
OVER_BUY_ZONE = 0.15       # 超过买入区间 15% 需重新评估

# iMessage 配置
IMSG_TO = "285336749@qq.com"


# ============================================================
# 工具函数
# ============================================================
def log(msg: str, verbose=False):
    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if verbose:
        print(f"  {line}")


def fetch_prices_tencent(codes: list[str]) -> dict:
    """从腾讯行情接口批量获取价格
    codes: A股代码列表，如 ['sh600276', 'sz000963', 'hk00570']
    返回: {code: {'name': ..., 'close': float, 'open': float, 'high': float, 'low': float}}
    """
    results = {}
    
    # 分批请求，避免被限流
    batch_size = 20
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        url = TENCENT_URL + ",".join(batch)
        
        try:
            import requests
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                log(f"  腾讯接口返回 HTTP {resp.status_code}")
                continue
            
            # 解析响应
            for line in resp.text.strip().split('\n'):
                line = line.strip()
                if not line or '=' not in line:
                    continue
                
                # 格式: v_sh600276="1~恒瑞医药~600276~54.34~..."
                match = re.match(r'v_(\w+)="(.+)"', line)
                if not match:
                    continue
                
                symbol = match.group(1)
                parts = match.group(2).split('~')
                
                # A股格式: 1~名称~代码~最新价~昨收~今开~...
                # 港股格式: 51~名称~代码~最新价~...
                if symbol.startswith('hk'):
                    # 港股: 51~名称~代码~最新价~昨收~今开~...
                    if len(parts) >= 4:
                        results[symbol] = {
                            'name': parts[1],
                            'close': float(parts[3]),
                            'prev_close': float(parts[4]) if len(parts) > 4 else None,
                        }
                else:
                    # A股: 1~名称~代码~最新价~昨收~今开~...
                    if len(parts) >= 6:
                        results[symbol] = {
                            'name': parts[1],
                            'close': float(parts[3]),
                            'prev_close': float(parts[4]),
                            'open': float(parts[5]),
                        }
                        if len(parts) >= 8:
                            results[symbol]['high'] = float(parts[6])
                            results[symbol]['low'] = float(parts[7])
                        
        except Exception as e:
            log(f"  请求失败: {str(e)[:80]}")
        
        time.sleep(0.5)  # 间隔避免限流
    
    return results


def classify_code(code: str) -> str:
    """将 stock_code 转换为腾讯符号"""
    code_num = code.split('.')[0]
    if code.endswith('.SH') or code_num.startswith('6'):
        return f"sh{code_num}"
    elif code.endswith('.SZ') or code_num.startswith(('0', '3')):
        return f"sz{code_num}"
    elif code.endswith('.HK'):
        return f"hk{code_num}"
    elif code.endswith('.BJ'):
        return f"bj{code_num}"
    return f"sh{code_num}"


def load_email_prices() -> dict:
    """从邮件提取的价格数据中加载（优先数据源）
    
    stock_mail_router.py 从 GitHub 日报提取的结构化价格表，
    以 {code: {'name', 'current_price', ...}} 格式保存。
    返回: {code: {'close': price, 'name': name, ...}} 与腾讯接口兼容
    """
    if not os.path.exists(PRICE_JSON):
        return {}
    
    try:
        with open(PRICE_JSON) as f:
            items = json.load(f)
    except Exception as e:
        log(f"  读取邮件价格数据失败: {e}")
        return {}
    
    prices = {}
    for item in items:
        code = item.get('stock_code', '')
        if not code or 'current_price' not in item:
            continue
        # 规范代码格式：去除 .SH/.SZ/.HK 后缀
        code_num = code.split('.')[0]
        prices[code_num] = {
            'close': item['current_price'],
            'name': item.get('stock_name', ''),
            'ma5': item.get('ma5'),
            'ma10': item.get('ma10'),
            'ma20': item.get('ma20'),
            'volume_ratio': item.get('volume_ratio'),
            'support_level': item.get('support_level'),
            'resistance_level': item.get('resistance_level'),
        }
    return prices


def fetch_prices_fallback(codes: list[str], email_prices: dict) -> dict:
    """价格获取：优先用邮件数据，缺失的用腾讯 API 补充"""
    if not email_prices:
        log("  邮件价格数据不可用，全部用腾讯 API 补充")
        return fetch_prices_tencent(codes)
    
    log(f"  邮件价格数据: {len(email_prices)} 只")
    
    # 找出邮件数据中没有的代码
    missing = []
    for c in codes:
        # 去除前缀 sh/sz/hk 提取纯代码
        code_num = c.lstrip('sh').lstrip('sz').lstrip('hk')
        if code_num not in email_prices:
            missing.append(c)
    
    if missing:
        log(f"  {len(missing)} 只股票邮件数据缺失，用腾讯 API 补充")
        tencent_prices = fetch_prices_tencent(missing)
    else:
        tencent_prices = {}
    
    # 合并：邮件优先，腾讯补充
    merged = {}
    for code_num, data in email_prices.items():
        # 构建腾讯符号
        if code_num.startswith('6'):
            symbol = f"sh{code_num}"
        elif code_num.startswith(('0', '3')):
            symbol = f"sz{code_num}"
        else:
            symbol = f"sh{code_num}"  # 默认
        merged[symbol] = data
    
    merged.update(tencent_prices)
    log(f"  合并后: {len(merged)} 个价格")
    return merged


def check_alerts(stocks: list[dict], prices: dict) -> list[dict]:
    """检查每只股票的预警状态"""
    alerts = []
    
    for stock in stocks:
        code = stock['stock_code']
        code_num = code.split('.')[0]
        symbol = classify_code(code)
        
        price_data = prices.get(symbol)
        if not price_data:
            continue
        
        current_price = price_data['close']
        buy_low = stock.get('buy_low')
        buy_high = stock.get('buy_high')
        sell_low = stock.get('sell_low')
        sell_high = stock.get('sell_high')
        
        if not buy_low:
            continue
        
        # 判断状态
        status = "normal"
        emoji = "⚪"
        alert_msg = ""
        
        if buy_low <= current_price <= buy_high:
            status = "buy_zone"
            emoji = "🟢"
            alert_msg = f"{emoji} **买入区间** {stock['stock_name']}({code}) ¥{current_price:.2f} | 区间: ¥{buy_low:.0f}-¥{buy_high:.0f}"
        elif sell_low and sell_low <= current_price <= sell_high:
            status = "sell_zone"
            emoji = "🔴"
            alert_msg = f"{emoji} **卖出区间** {stock['stock_name']}({code}) ¥{current_price:.2f} | 区间: ¥{sell_low:.0f}-¥{sell_high:.0f}"
        elif current_price > buy_high:
            pct_over = (current_price - buy_high) / buy_high * 100
            if pct_over > OVER_BUY_ZONE:
                status = "over_buy"
                emoji = "⚠️"
                alert_msg = f"{emoji} **超买入区间{pct_over:.0f}%** {stock['stock_name']}({code}) ¥{current_price:.2f} | 区间: ¥{buy_low:.0f}-¥{buy_high:.0f} | 需重新评估"
            elif pct_over > BUY_ZONE_WARNING * 100:
                status = "near_sell"
                emoji = "💡"
                alert_msg = f"{emoji} **接近卖出区间** {stock['stock_name']}({code}) ¥{current_price:.2f} | 距卖出区间¥{sell_low:.0f}差{(sell_low-current_price)/current_price*100:.1f}%"
        elif current_price < buy_low:
            pct_under = (buy_low - current_price) / buy_low * 100
            if pct_under > BUY_ZONE_WARNING * 100:
                status = "below_buy"
                emoji = "💡"
                alert_msg = f"{emoji} **低于买入区间** {stock['stock_name']}({code}) ¥{current_price:.2f} | 区间: ¥{buy_low:.0f}-¥{buy_high:.0f} | 低{pct_under:.1f}%"
        
        if alert_msg:
            alerts.append({
                'stock_name': stock['stock_name'],
                'stock_code': code,
                'current_price': current_price,
                'buy_low': buy_low,
                'buy_high': buy_high,
                'sell_low': sell_low,
                'sell_high': sell_high,
                'status': status,
                'emoji': emoji,
                'message': alert_msg,
            })
    
    return alerts


def send_imessage(message: str, dry_run=False):
    """通过 iMessage 推送"""
    # 截断消息到合理长度
    if len(message) > 500:
        message = message[:497] + "..."
    
    cmd = [
        "imsg", "send",
        "--to", IMSG_TO,
        "--text", message,
        "--service", "imessage"
    ]
    
    if dry_run:
        log(f"[DRY-RUN] 会发送: {message}")
        return True
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            log(f"✅ iMessage 已发送")
            return True
        else:
            log(f"❌ iMessage 发送失败: {result.stderr[:200]}")
            return False
    except FileNotFoundError:
        log(f"❌ imsg 命令不存在，跳过推送")
        return False
    except Exception as e:
        log(f"❌ iMessage 发送异常: {e}")
        return False


def run(dry_run=False, verbose=False, cron=False):
    """主流程"""
    _null = None
    if cron:
        log_enabled = False
        notify_on_complete = True
        _null = open(os.devnull, "w")
        stdout_mgr = redirect_stdout(_null)
    else:
        log_enabled = True
        notify_on_complete = False
        stdout_mgr = nullcontext()

    with stdout_mgr:
        def _log(msg, force=False):
            if log_enabled or force:
                log(msg, verbose)

        _log("=" * 60)
        _log(f"股票价格预警系统启动 (dry_run={dry_run})")
        _log(f"日期: {TODAY}")

        # 1. 加载投资组合数据
        if not os.path.exists(PORTFOLIO_JSON):
            msg = f"❌ 找不到数据文件: {PORTFOLIO_JSON}"
            _log(msg, force=cron)
            if cron:
                send_imessage(f"[price_alert] {msg}", dry_run)
            return

        with open(PORTFOLIO_JSON) as f:
            stocks = json.load(f)

        _log(f"加载 {len(stocks)} 只股票")

        # 2. 筛选有买卖计划的股票
        planned_stocks = [s for s in stocks if s.get('buy_low')]
        _log(f"有买卖计划: {len(planned_stocks)} 只")

        # 3. 获取所有需要查询的代码
        all_codes = [classify_code(s['stock_code']) for s in stocks if s.get('buy_low')]
        unique_codes = list(set(all_codes))
        _log(f"需要查询: {len(unique_codes)} 个代码")

        # 4. 加载邮件价格数据（优先）+ 腾讯 API 补充
        _log("加载邮件价格数据...")
        email_prices = load_email_prices()

        _log("获取价格...")
        prices = fetch_prices_fallback(unique_codes, email_prices)
        _log(f"获取到 {len(prices)} 个价格")

        # 5. 检查预警
        alerts = check_alerts(stocks, prices)

        if not alerts:
            _log("✅ 无预警", force=True)
            if cron:
                # cron 模式无预警也推一条简洁确认
                send_imessage(f"[price_alert] {TODAY} 无预警 ✅", dry_run)
            return

        # 6. 生成汇总消息
        summary_parts = [
            f"📊 股票预警 {TODAY}",
            f"共 {len(alerts)} 只触发预警",
            "",
        ]

        # cron 模式精简输出，交互模式全量
        if cron:
            # 只按状态分组统计，不全列
            status_summary = defaultdict(list)
            for a in alerts:
                status_summary[a['status']].append(a['stock_name'])
            for status, names in sorted(status_summary.items()):
                summary_parts.append(f"{status}: {len(names)}只 — {'、'.join(names[:5])}{'...' if len(names)>5 else ''}")
            summary_parts.append("")
            summary_parts.append("详情见 alert_log.jsonl")
        else:
            for alert in alerts:
                summary_parts.append(alert['message'])

        summary = "\n".join(summary_parts)

        # 7. 推送 iMessage
        _log(f"\n{'='*60}")
        _log(f"预警消息:\n{summary}")
        _log(f"{'='*60}")

        send_imessage(summary, dry_run)

        # 8. 保存日志
        if not dry_run:
            log_dir = os.path.dirname(ALERT_LOG)
            os.makedirs(log_dir, exist_ok=True)
            with open(ALERT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    'date': TODAY,
                    'alert_count': len(alerts),
                    'alerts': alerts,
                    'message': summary,
                    'mode': 'cron' if cron else 'interactive',
                }, ensure_ascii=False) + "\n")
            _log(f"日志已保存: {ALERT_LOG}")

    if _null is not None:
        _null.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="股票价格预警系统")
    parser.add_argument("--dry-run", action="store_true", help="只模拟不执行写操作")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    parser.add_argument("--cron", action="store_true", help="cron 静默模式，精简输出")
    args = parser.parse_args()
    run(dry_run=args.dry_run, verbose=args.verbose, cron=args.cron)
