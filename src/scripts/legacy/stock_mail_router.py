#!/usr/bin/env python3
"""
stock_mail_router.py — 股票邮件路由器
===================================
1. 读取 agent.qq.com 收件箱中当日股票分析邮件（关键词 "股票分析" / "每日股票分析"）
2. 区分简洁版 vs 复杂版，只保留复杂版
3. 将复杂版内容保存到 workspace
4. 清理简洁版邮件（移到已删除）

用法：
    python stock_mail_router.py [--dry-run]

说明：
- 简洁版通常短（< 3000 字），复杂版长（> 3000 字）
- 当日邮件通过日期过滤，只处理今天或昨天的邮件
- 简洁版邮件会移到 trash（不直接删除）
"""

from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

# ============================================================
# 配置
# ============================================================
WORKSPACE = os.environ.get(
    "HERMES_WORKSPACE",
    os.path.expanduser("~/.hermes/workspace"),
)
OUTPUT_DIR = os.path.join(WORKSPACE, "stock_daily")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "latest_full_report.md")
LOG_FILE = os.path.join(OUTPUT_DIR, "stock_mail_router.log")

TODAY = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
SEARCH_WINDOW_DAYS = 2  # 搜索范围：今天 + 昨天


def run_cmd(cmd: list[str], capture: bool = True) -> subprocess.CompletedProcess:
    """运行 agently-cli 命令"""
    env = os.environ.copy()
    return subprocess.run(
        cmd,
        capture_output=capture,
        text=True,
        env=env,
        timeout=120,
    )


def log(msg: str):
    """写日志到文件 + 控制台"""
    ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def parse_date_from_subject_or_body(subject, body):
    """尝试从邮件主题或正文提取日期 YYYY-MM-DD
    优先用主题中的日期（如"📈 股票智能分析报告 - 2026-07-10"），
    不限制窗口天数，允许处理积压邮件。
    """
    date_patterns = [
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(\d{4})年(\d{1,2})月(\d{1,2})日",
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
    ]
    text = (subject or "") + " " + (body or "")[:2000]
    for pat in date_patterns:
        m = re.search(pat, text)
        if m:
            y, m_, d = m.groups()
            try:
                dt = datetime(int(y), int(m_), int(d), tzinfo=timezone(timedelta(hours=8)))
                # 不限制窗口天数，允许处理积压邮件
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def search_stock_emails():
    """搜索收件箱中的股票分析邮件（今天+昨天）"""
    after = (
        datetime.now(timezone(timedelta(hours=8)))
        - timedelta(days=SEARCH_WINDOW_DAYS)
    ).strftime("%Y-%m-%d")

    log(f"搜索股票分析邮件，after={after}")

    # 第1步：搜索邮件（QQ邮箱搜索不支持OR语法，用单关键词）
    result = run_cmd([
        "agently-cli", "message", "+search",
        "--q", "股票智能分析报告",
        "--after", after,
        "--limit", "20",
    ])

    if result.returncode != 0:
        log(f"搜索失败: {result.stderr[:500]}")
        return []

    try:
        data = json.loads(result.stdout)
        messages = data.get("data", {}).get("data", [])
    except (json.JSONDecodeError, KeyError) as e:
        log(f"解析搜索结果失败: {e}")
        return []

    log(f"找到 {len(messages)} 封相关邮件")
    return messages


def read_message(msg_id):
    """读取单封邮件完整内容"""
    result = run_cmd(["agently-cli", "message", "+read", "--id", msg_id])
    if result.returncode != 0:
        log(f"读取邮件失败: {result.stderr[:300]}")
        return None
    try:
        data = json.loads(result.stdout)
        return data.get("data", {})
    except (json.JSONDecodeError, KeyError) as e:
        log(f"解析邮件内容失败: {e}")
        return None


def get_text_content(msg):
    """提取邮件正文文本（HTML → 纯文本）"""
    # agently-cli 返回 body 在顶层
    body = msg.get("body", "")
    if not body:
        body = msg.get("content", "") or ""
    if isinstance(body, dict):
        body = body.get("text", "") or body.get("html", "") or body.get("body", "")
    
    if not body:
        return ""
    
    # HTML → 纯文本：去 tag，保留基本结构
    import re
    text = re.sub(r"<style[^>]*>.*?</style>", "", body, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|tr|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;|&#38;", "&", text)
    text = re.sub(r"&lt;|&#60;", "<", text)
    text = re.sub(r"&gt;|&#62;", ">", text)
    text = text.strip()
    return text


def trash_message(msg_id, dry_run=False):
    """将邮件移到已删除"""
    if dry_run:
        log(f"[DRY-RUN] 会删除简洁版邮件: {msg_id}")
        return True

    result = run_cmd(["agently-cli", "message", "+trash", "--id", msg_id])
    if result.returncode == 0:
        log(f"已归档简洁版邮件: {msg_id}")
        return True
    else:
        log(f"归档失败: {result.stderr[:300]}")
        return False


def is_simple_version(subject: str, body: str) -> bool:
    """判断是否为简洁版邮件
    规则：
    - 主题含"简报"/"summary"/"速览"等关键词
    - 或正文 < 2000 字且不含深度分析关键词
    """
    subject_lower = subject.lower()
    body_lower = body.lower()

    # 主题关键词判断
    simple_keywords = ["简报", "summary", "速览", "digest", "快报", "brief"]
    complex_keywords = ["详细", "full", "完整", "复杂", "深度", "analysis", "report"]

    for kw in simple_keywords:
        if kw in subject_lower:
            return True
    for kw in complex_keywords:
        if kw in subject_lower:
            return False

    # 长度判断
    if len(body) < 2000:
        return True
    if len(body) > 5000:
        return False

    # 内容关键词判断
    if "深度分析" in body or "技术面分析" in body or "策略建议" in body:
        return False

    # 默认：长度在中间地带的，视为简洁版（保守处理）
    return True


def save_report(subject, body, date_str, dry_run=False):
    """保存复杂版报告到 workspace"""
    # 使用邮件实际日期，无法提取时用 processing 日期
    report_date = date_str or TODAY
    filename = f"stock_report_{report_date}.md"
    filepath = os.path.join(OUTPUT_DIR, filename)

    # 同时保存最新软链接
    content = f"# {subject}\n\n{body}\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    # 更新 latest_full_report.md
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    log(f"已保存复杂版报告: {filepath}")


def extract_price_table(body_html: str, date_str: str) -> list[dict]:
    """从邮件 HTML 中提取结构化价格表

    NOTE: GitHub Actions 邮件渲染为嵌套 HTML 表格，结构不稳定。
    该方法已废弃，保留接口兼容。价格数据改用腾讯 API 实时获取。
    """
    return []


def save_price_data(prices: list[dict], dry_run: bool = False) -> str:
    """保存提取的价格数据到 JSON 文件"""
    filepath = os.path.join(OUTPUT_DIR, f"stock_prices_{TODAY}.json")
    
    if dry_run:
        log(f"[DRY-RUN] 会保存 {len(prices)} 条价格到 {filepath}")
        return filepath
    
    # 追加模式：读已有数据合并，保留最新日期优先
    existing = {}
    if os.path.exists(filepath):
        try:
            with open(filepath) as f:
                existing = {item['stock_code']: item for item in json.load(f)}
        except Exception:
            pass
    
    for item in prices:
        existing[item['stock_code']] = item
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(list(existing.values()), f, ensure_ascii=False, indent=2)
    
    log(f"价格数据已保存: {filepath} ({len(existing)} 只股票)")
    return filepath


def run(dry_run: bool = False):
    """主流程"""
    ensure_output_dir()
    log("=" * 60)
    log(f"stock_mail_router 启动 (dry_run={dry_run})")
    log(f"日期: {TODAY}")

    # 1. 搜索邮件
    messages = search_stock_emails()
    if not messages:
        log("未找到当日股票分析邮件")
        return

    complex_versions = []
    simple_count = 0
    all_prices = []

    # 2. 逐封读取、分类
    for msg in messages:
        msg_id = msg.get("message_id", "")
        subject = msg.get("subject", "")
        snippet = msg.get("snippet", "")

        log(f"处理邮件: {msg_id} | {subject[:80]}")

        detail = read_message(msg_id)
        if not detail:
            continue

        body = get_text_content(detail)
        if not body:
            log(f"  空正文，跳过")
            continue

        # 从原始 HTML 中提取结构化价格表（在 HTML 层面提取，不依赖文本转换）
        raw_html = detail.get("body", "")
        if isinstance(raw_html, dict):
            raw_html = raw_html.get("html", raw_html.get("text", ""))
        if raw_html:
            date_str = parse_date_from_subject_or_body(subject, body)
            prices = extract_price_table(raw_html, date_str)
            if prices:
                log(f"  提取到 {len(prices)} 条结构化价格数据")
                all_prices.extend(prices)

        if not body:
            continue

        date_str = parse_date_from_subject_or_body(subject, body)
        log(f"  正文长度: {len(body)} 字 | 识别日期: {date_str or '未知'}")

        if is_simple_version(subject, body):
            log(f"  → 简洁版，清理中...")
            trash_message(msg_id, dry_run)
            simple_count += 1
        else:
            log(f"  → 复杂版，保留")
            save_report(subject, body, date_str, dry_run)
            complex_versions.append((msg_id, subject, date_str))

    # 3. 保存结构化价格数据
    if all_prices:
        save_price_data(all_prices, dry_run)
        log(f"汇总: {len(all_prices)} 条价格数据已提取")

    log(f"处理完成: 复杂版 {len(complex_versions)} 封, 简洁版 {simple_count} 封")
    if not complex_versions:
        log("⚠️ 未找到复杂版报告")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="股票邮件路由器")
    parser.add_argument("--dry-run", action="store_true", help="只模拟不执行写操作")
    args = parser.parse_args()
    run(dry_run=args.dry_run)