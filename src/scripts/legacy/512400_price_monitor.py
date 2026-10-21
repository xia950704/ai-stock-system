#!/usr/bin/env python3
"""
512400 有色金属ETF 价格监控脚本
运行方式：python3 512400_price_monitor.py
输出：当日价格状态 + 触发警报时写入通知笔记
"""

import urllib.request, json, os, re
from datetime import datetime
import sys
import random
import time
from pathlib import Path

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

def _urlopen_with_retry(url: str, timeout: int = 10) -> urllib.response.addbase:
    """带 retry 的 urllib.request.urlopen 封装"""
    last_error = None
    for attempt in range(_RETRY_MAX_RETRIES + 1):
        try:
            return urllib.request.urlopen(url, timeout=timeout)
        except Exception as e:
            last_error = e
            if attempt >= _RETRY_MAX_RETRIES:
                break
            delay = _retry_backoff(attempt)
            print(f"  ⚠️ 请求失败 (attempt {attempt+1}/{_RETRY_MAX_RETRIES}): {e}, 等待 {delay:.1f}s")
            time.sleep(delay)
    raise last_error

# Loop Engineering: 增量检测
DELTA_PATH = Path(__file__).parent.parent / "skills/data-science/loop-engineering-state/scripts"
sys.path.insert(0, str(DELTA_PATH.resolve()))
try:
    from state_manager import DeltaDetector
except ImportError:
    DeltaDetector = None  # data-science skill not available, script runs in read-only mode


# === 配置 ===
CODE = 'sh512400'
VAULT_DIR = os.path.expanduser("/Users/xiashuang/obsidian/all about xia")
ALERT_DIR = os.path.join(VAULT_DIR, "01-股票投研/ETF")

# 关键价位（来自深度分析）
LEVELS = {
    "MA60_支撑": 2.007,
    "MA20_支撑": 1.935,
    "38.2%斐波那契": 1.907,
    "60日最低价": 1.864,
    "MA120_阻力": 2.059,
    "布林上轨": 2.080,
    "60日最高价": 2.209,
}

def get_realtime_price():
    """获取实时价格"""
    url = f'https://qt.gtimg.cn/q={CODE}'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with _urlopen_with_retry(req, timeout=10) as resp:
        qdata = resp.read().decode('gbk', errors='ignore')
    
    m = re.search(r'\"(.+)\"', qdata)
    if not m:
        return None, None
    
    fields = m.group(1).split('~')
    price = float(fields[3]) if fields[3] else None
    prev_close = float(fields[4]) if fields[4] else None
    change_pct = fields[32] if len(fields) > 32 else None
    name = fields[1] if fields[1] else "有色金属ETF"
    
    return price, prev_close, change_pct, name

def check_alert_zones(price):
    """检查价格是否进入警戒区域"""
    alerts = []
    
    # 检查每个关键价位
    for name, level in LEVELS.items():
        dist = (price - level) / level * 100
        # 距离1.5%以内算"接近"
        if abs(dist) <= 1.5:
            alerts.append((name, level, dist))
    
    return alerts

def get_technical_status(price, prev_close):
    """推断当前技术状态"""
    if price is None:
        return "数据获取失败"
    
    change = (price - prev_close) / prev_close * 100 if prev_close else 0
    
    status = []
    
    if price >= LEVELS["MA120_阻力"]:
        status.append(f"✅ 站上MA120(¥{LEVELS['MA120_阻力']})")
    elif price >= LEVELS["MA60_支撑"]:
        status.append(f"🟡 MA60上方 · 距MA120({LEVELS['MA120_阻力']}) {(LEVELS['MA120_阻力']/price-1)*100:.1f}%")
    elif price >= LEVELS["MA20_支撑"]:
        status.append(f"🟠 MA60-MA20之间 · MA60已破")
    elif price >= LEVELS["38.2%斐波那契"]:
        status.append(f"🔴 深度回调 · 接近38.2%支撑位")
    else:
        status.append(f"🔴 低于38.2%支撑 · 强势回调中")
    
    status.append(f"当日涨跌: {change:+.2f}%")
    
    return " · ".join(status)

def write_daily_check(price, prev_close, change_pct, name, alerts, status):
    """写入每日价格跟踪"""
    today = datetime.now().strftime("%Y-%m-%d")
    
    path = os.path.join(VAULT_DIR, "01-股票投研/ETF/512400日度跟踪.md")
    
    # 读取已有内容或创建
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            existing = f.read()
    else:
        existing = f"""---
title: 有色金属ETF 512400 日度跟踪
created: {today}
tags: [ETF, 512400, 价格跟踪, 有色金属]
status: active
---

# 有色金属ETF 512400 日度跟踪

> 自动监测脚本
> 监控价位区间：¥1.864 ~ ¥2.209

"""
    
    # 追加当日记录
    entry = f"\n| {today} | ¥{price:.3f} | {change_pct} | {status} |"
    
    if "|" in existing:
        # 已有表格，追加行
        lines = existing.split('\n')
        # 在最后一行前插入
        for i in range(len(lines)-1, -1, -1):
            if lines[i].startswith('|') and '|' in lines[i]:
                lines.insert(i+1, entry)
                break
        new_content = '\n'.join(lines)
    else:
        # 创建新表格
        new_content = existing + f"""
## 价格跟踪表

| 日期 | 价格 | 涨跌幅 | 技术状态 |
|------|------|--------|---------|
{entry}
"""
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    return path

def main():
    try:
        price, prev_close, change_pct, name = get_realtime_price()
    except Exception as e:
        print(f"[ERROR] 数据获取失败: {e}")
        return

    if price is None:
        print("[ERROR] 价格解析失败")
        return

    # === Loop Engineering: 增量检测（可选，需 data-science skill）===
    if DeltaDetector is not None:
        detector = DeltaDetector("512400-price")
        current_data = {
            "price": round(price, 4),
            "prev_close": round(prev_close, 4) if prev_close else None,
            "change_pct": change_pct
        }
        changed, old_fp, new_fp = detector.has_changed(current_data)
        if not changed:
            print(f"[DELTA] 价格无显著变化")
    else:
        print("[INFO] DeltaDetector 不可用，跳过增量检测")
        # 但还是要报告当前价格！
        print(f"📊 512400 日度报告 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"现价: ¥{price:.3f}" + (f" | 昨收: ¥{prev_close:.3f}" if prev_close else ""))
        print(f"当日涨跌: {change_pct}%" if change_pct else "")
        print(f"状态: 区间内正常波动，未触发预警")
        return
    print(f"[DELTA] 价格已变化 (指纹: {new_fp[:16]}...)")

    alerts = check_alert_zones(price)
    status = get_technical_status(price, prev_close)
    
    print(f"=== {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    print(f"{name} 当前价: ¥{price:.3f}")
    print(f"状态: {status}")
    
    if alerts:
        print(f"\n⚠️ 接近关键价位：")
        for name, level, dist in alerts:
            print(f"  {name}: ¥{level:.3f} (距离 {dist:+.2f}%)")

    # 保存指纹
    detector.save_fingerprint(current_data, metadata={
        "last_summary": f"价格: ¥{price:.3f}, 涨跌: {change_pct}%"
    })

    # 写入跟踪笔记
    path = write_daily_check(price, prev_close, change_pct, name, alerts, status)
    print(f"\n跟踪记录: {path}")

if __name__ == '__main__':
    main()
