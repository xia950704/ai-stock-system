#!/usr/bin/env python3
"""配置验证脚本（P3-0）— 检查环境变量、路径和配置契约。

用法:
    python3 validate_stock_config.py [--strict]

--strict: 发现任何警告也返回非零退出状态
"""
import json
import os
import sys
from pathlib import Path

def expand(path):
    return os.path.expanduser(path)

def check_env_var(name, required=False, default=None):
    """检查环境变量是否存在，返回 (值，是否使用默认值，信息)"""
    val = os.environ.get(name)
    if val is None:
        if required:
            return None, True, f"❌ {name} 未设置（必需）"
        if default is not None:
            return default, True, f"⚠️ {name} 未设置，使用默认值：{default}"
        return None, True, f"⚠️ {name} 未设置"
    return val, False, f"✅ {name} = {val}"

def check_path_exists(path, name, must_exist=False, must_be_dir=False):
    """检查路径是否存在"""
    expanded = expand(path)
    p = Path(expanded)
    if must_exist:
        if not p.exists():
            return False, f"❌ {name} 不存在：{expanded}"
        if must_be_dir and not p.is_dir():
            return False, f"❌ {name} 不是目录：{expanded}"
        return True, f"✅ {name} 存在：{expanded}"
    # 仅提示路径
    if p.exists():
        return True, f"✅ {name} 存在：{expanded}"
    return True, f"ℹ️ {name} 不存在（可接受）：{expanded}"

def main():
    strict = "--strict" in sys.argv
    errors = []
    warnings = []
    info = []

    print("=" * 60)
    print("股票投研系统配置验证（P3-0）")
    print("=" * 60)
    print()

    # 1. 检查 DATA_ROOT
    data_root, used_default, msg = check_env_var("DATA_ROOT", required=False, default="~/harness")
    info.append(msg)
    if used_default:
        warnings.append("DATA_ROOT 使用默认值")
    data_root_path = expand(data_root)

    # 2. 检查 STOCK_DAILY_DIR
    stock_daily, used_default, msg = check_env_var("STOCK_DAILY_DIR", required=False, default="~/harness/stock_daily")
    info.append(msg)
    if used_default:
        warnings.append("STOCK_DAILY_DIR 使用默认值")
    stock_daily_path = expand(stock_daily)

    # 3. 检查 HERMES_WORKSPACE_DIR
    hermes_ws, used_default, msg = check_env_var("HERMES_WORKSPACE_DIR", required=False, default="~/.hermes/workspace")
    info.append(msg)
    if used_default:
        warnings.append("HERMES_WORKSPACE_DIR 使用默认值")
    hermes_ws_path = expand(hermes_ws)

    # 4. 验证路径存在性
    exists, msg = check_path_exists(data_root_path, "DATA_ROOT", must_exist=True, must_be_dir=True)
    if exists:
        info.append(msg)
    else:
        errors.append(msg)

    exists, msg = check_path_exists(stock_daily_path, "STOCK_DAILY_DIR", must_exist=True, must_be_dir=True)
    if exists:
        info.append(msg)
    else:
        errors.append(msg)

    exists, msg = check_path_exists(hermes_ws_path, "HERMES_WORKSPACE_DIR", must_exist=False, must_be_dir=True)
    info.append(msg)  # 仅提示级别

    # 5. 检查关键文件
    anchor_path = os.path.join(data_root_path, "anchor_status.json")
    exists, msg = check_path_exists(anchor_path, "anchor_status.json", must_exist=True)
    if exists:
        info.append(msg)
        # 验证 JSON 格式
        try:
            with open(anchor_path) as f:
                data = json.load(f)
            if isinstance(data, list) and len(data) > 0:
                info.append(f"✅ anchor_status.json 有效：{len(data)} 条记录")
            else:
                warnings.append("⚠️ anchor_status.json 格式异常（应为非空数组）")
        except json.JSONDecodeError as e:
            errors.append(f"❌ anchor_status.json JSON 解析失败：{e}")
    else:
        errors.append(msg)

    # 6. 检查配置契约一致性
    info.append("")
    info.append("=== 环境变量契约 ===")
    info.append("DATA_ROOT: 数据根目录，默认 ~/harness")
    info.append("  - 用于：anchor_status.json, backup_phase1/")
    info.append("  - 被读取：update_anchor.py, fetch_realtime.py")
    info.append("")
    info.append("STOCK_DAILY_DIR: 股票日常数据目录，默认 ~/harness/stock_daily")
    info.append("  - 用于：realtime_prices_*.json, stock_ranking.json, backtest_signals.json")
    info.append("  - 被读取：stock_signal_extractor.py, stock_ranking.py, backtest_*.py")
    info.append("")
    info.append("HERMES_WORKSPACE_DIR: Hermes 工作目录，默认 ~/.hermes/workspace")
    info.append("  - 用于：ml_trend_predictions.json")
    info.append("  - 被读取：stock_ranking.py")
    info.append("")

    # 7. 输出结果
    for line in info:
        print(line)

    if warnings:
        print("\n=== 警告 ===")
        for w in warnings:
            print(w)

    if errors:
        print("\n=== 错误 ===")
        for e in errors:
            print(e)

    print()
    print("=" * 60)
    if errors:
        print(f"结果：❌ 失败（{len(errors)} 错误，{len(warnings)} 警告）")
        sys.exit(1)
    elif strict and warnings:
        print(f"结果：⚠️ 通过但有警告（--strict 模式）（{len(warnings)} 警告）")
        sys.exit(1)
    else:
        print(f"结果：✅ 通过（{len(warnings)} 警告）")
        sys.exit(0)

if __name__ == "__main__":
    main()
