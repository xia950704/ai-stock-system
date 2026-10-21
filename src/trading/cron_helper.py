#!/usr/bin/env python3
"""
Cron 配置助手 — 生成 / 安装 crontab 条目

用法:
  python3 cron_helper.py                           # 打印 crontab 配置
  python3 cron_helper.py --install                 # 自动安装到 crontab
  python3 cron_helper.py --remove                  # 移除本项目的 crontab 条目

项目路径: {PROJECT_DIR}
"""
import os, subprocess, re

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(PROJECT_DIR, 'run.py')
PAIRS = os.path.join(PROJECT_DIR, 'run.py')  # 都用run.py
LOG_DIR = os.path.join(PROJECT_DIR, 'logs')

# ==================== 定时任务定义 ====================
CRON_ENTRIES = [
    # ── ML 策略（已弃用，保留不删） ──
    ("# ═══════════════════════════════════════════", "分隔线"),
    ("# 📈 股票交易策略系统 - 定时任务", "标题"),

    # ── 配对交易（主要） ──
    ("# 交易日 15:17 收盘后检查配对信号", "注释"),
    ("17 15 * * 1-5 cd {d} && python3 {r} pairs signal >> {l}/pairs_signal.log 2>&1".format(
        d=PROJECT_DIR, r=RUN, l=LOG_DIR), "配对信号"),

    ("# 交易日 15:20 生成每日报告（Obsidian + HTML）", "注释"),
    ("20 15 * * 1-5 cd {d} && python3 {r} pairs report >> {l}/pairs_report.log 2>&1".format(
        d=PROJECT_DIR, r=RUN, l=LOG_DIR), "每日报告"),

    ("# 交易日 15:22 自动执行交易（Codex模式）", "注释"),
    ("22 15 * * 1-5 cd {d} && python3 {r} pairs trade >> {l}/auto_trade.log 2>&1".format(
        d=PROJECT_DIR, r=RUN, l=LOG_DIR), "自动交易"),

    ("# 周六 9:17 跑全配对回测周报", "注释"),
    ("17 9 * * 6 cd {d} && python3 {r} pairs backtest >> {l}/pairs_weekly.log 2>&1".format(
        d=PROJECT_DIR, r=RUN, l=LOG_DIR), "配对周报"),

    # ── ML（保留） ──
    ("# 交易日 9:30 开盘前刷新 ML 信号", "注释"),
    ("30 9 * * 1-5 cd {d} && python3 {r} ml --mode signal >> {l}/ml_signal.log 2>&1".format(
        d=PROJECT_DIR, r=RUN, l=LOG_DIR), "ML信号"),

    ("", "空行"),
]


def print_crontab():
    """打印 crontab 配置"""
    print("# ═══════════════════════════════════════════")
    print("# 📈 股票交易策略系统 - Crontab 配置")
    print("#   生成时间: $(date)")
    print("# ═══════════════════════════════════════════")
    print(f"# 项目目录: {PROJECT_DIR}")
    print(f"# 统一入口: {RUN}")
    print(f"# 日志目录: {LOG_DIR}")
    print("#")
    for entry, _ in CRON_ENTRIES:
        print(entry)
    print("# ═══════════════════════════════════════════")
    print("# 手动执行示例:")
    print(f"#   python3 {RUN} pairs signal")
    print(f"#   python3 {RUN} pairs backtest")
    print(f"#   python3 {RUN} pairs 600519,000858")
    print("# ═══════════════════════════════════════════")


def get_current_crontab():
    """获取当前 crontab 内容"""
    try:
        result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else ''
    except FileNotFoundError:
        return ''


def install():
    """安装本项目定时任务"""
    os.makedirs(LOG_DIR, exist_ok=True)

    current = get_current_crontab()
    entries = [e for e, _ in CRON_ENTRIES if e and not e.startswith('#') and not e.startswith(' ')]

    new_cron = current.rstrip()
    if new_cron and not new_cron.endswith('\n'):
        new_cron += '\n'
    new_cron += '\n# ── 股票交易系统（自动安装） ──\n'
    for entry in entries:
        new_cron += entry + '\n'

    with subprocess.Popen(['crontab'], stdin=subprocess.PIPE, text=True) as proc:
        proc.communicate(new_cron)

    print(f"✅ 已安装 {len(entries)} 条定时任务")
    for e in entries:
        schedule, _, command = e.partition(' ')
        print(f"   {schedule} → {command[:40]}...")


def remove():
    """移除本项目定时任务"""
    current = get_current_crontab()
    cleaned = re.sub(r'\n# ── 股票交易系统（自动安装） ──\n.*?(?=\n# ──|\Z)', '', current, flags=re.DOTALL)

    with subprocess.Popen(['crontab'], stdin=subprocess.PIPE, text=True) as proc:
        proc.communicate(cleaned)

    print("✅ 已移除股票交易系统定时任务")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='股票交易系统 cron 配置助手')
    parser.add_argument('--install', action='store_true', help='安装定时任务')
    parser.add_argument('--remove', action='store_true', help='移除定时任务')
    args = parser.parse_args()

    if args.remove:
        remove()
    elif args.install:
        install()
    else:
        print_crontab()


if __name__ == '__main__':
    main()