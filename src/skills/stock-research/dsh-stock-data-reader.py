#!/usr/bin/env python3
"""
DSH 股票数据读取测试
用于验证 DSH 能否正确读取 Hermes 投资数据
"""
import os
import json
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# 配置路径
HERMES_WORKSPACE = Path.home() / ".hermes" / "workspace"
STOCK_DAILY_DIR = HERMES_WORKSPACE / "stock_daily"
OBSIDIAN_VAULT = Path("/Users/xiashuang/obsidian/all about xia")
STOCK_INVEST_DIR = OBSIDIAN_VAULT / "01-股票投研"

# 时区
CST = timezone(timedelta(hours=8))

def log(msg: str, level: str = "info"):
    """格式化日志输出"""
    ts = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    prefix = "[ERROR]" if level == "error" else ("[WARN]" if level == "warning" else "")
    print(f"[{ts}] {prefix} {msg}")

def read_daily_check_files():
    """读取每日检查CSV文件"""
    log("读取每日检查文件...")
    
    if not STOCK_DAILY_DIR.exists():
        log(f"目录不存在: {STOCK_DAILY_DIR}", level="error")
        return None
    
    # 查找最新的每日检查文件（实际格式为 .md）
    files = sorted(STOCK_DAILY_DIR.glob("每日股票检查_*.md"), reverse=True)
    if not files:
        log("未找到每日检查文件", level="warning")
        return None
    
    latest_file = files[0]
    log(f"最新文件: {latest_file.name}")
    
    # 读取CSV（兼容 .csv 和 .md 格式）
    try:
        import pandas as pd
        if latest_file.suffix == '.csv':
            df = pd.read_csv(latest_file)
            result = {
                "file": latest_file.name,
                "total_rows": len(df),
                "columns": list(df.columns),
                "sample": df.head(5).to_dict('records')
            }
            log(f"成功读取 {len(df)} 行数据")
            return result
        else:
            # .md 文件：返回前 20 行原文
            with open(latest_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[:20]
            result = {
                "file": latest_file.name,
                "total_lines": len(lines),
                "sample": [l.rstrip('\n') for l in lines]
            }
            log(f"成功读取 {latest_file.name}（markdown 格式，前 20 行）")
            return result
        
    except Exception as e:
        log(f"读取失败: {e}", level="error")
        return None

def read_gfdma_data():
    """读取GF-DMA健康度评分"""
    log("读取GF-DMA评分...")
    
    bayesian_dir = STOCK_DAILY_DIR / "bayesian"
    if not bayesian_dir.exists():
        log(f"目录不存在: {bayesian_dir}", level="warning")
        return None
    
    # 查找最新评分文件
    files = sorted(bayesian_dir.glob("Bayesian_H0H5_概率更新_*.json"), reverse=True)
    if not files:
        log("未找到GF-DMA评分文件", level="warning")
        return None
    
    latest_file = files[0]
    log(f"最新文件: {latest_file.name}")
    
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取P0核心股
        p0_codes = ['600276', '000963', '603259', '002422', '688331']
        p0_scores = []
        
        for code, info in data.items():
            if code in p0_codes:
                p0_scores.append({
                    "code": code,
                    "score": info.get("score"),
                    "level": info.get("level"),
                    "probability": info.get("probability")
                })
        
        result = {
            "file": latest_file.name,
            "total_stocks": len(data),
            "p0_stocks": p0_scores
        }
        
        log(f"成功读取 {len(data)} 只股票评分")
        return result
        
    except Exception as e:
        log(f"读取失败: {e}", level="error")
        return None

def read_stock_portfolio():
    """读取投资组合配置"""
    log("读取投资组合...")
    
    portfolio_file = HERMES_WORKSPACE / "stock_portfolio_enriched.json"
    if not portfolio_file.exists():
        log(f"文件不存在: {portfolio_file}", level="warning")
        return None
    
    try:
        with open(portfolio_file, 'r', encoding='utf-8') as f:
            portfolio = json.load(f)
        
        result = {
            "total_stocks": len(portfolio.get("stocks", [])),
            "p0_stocks": [
                s for s in portfolio.get("stocks", []) 
                if s.get("priority") == "P0"
            ],
            "summary": portfolio.get("summary", {})
        }
        
        log(f"成功读取 {result['total_stocks']} 只股票配置")
        return result
        
    except Exception as e:
        log(f"读取失败: {e}", level="error")
        return None

def read_investment_notes(stock_code: str = None):
    """读取个股投资笔记"""
    log(f"读取投资笔记{' (' + stock_code + ')' if stock_code else ''}...")
    
    stocks_dir = STOCK_INVEST_DIR / "股票"
    if not stocks_dir.exists():
        log(f"目录不存在: {stocks_dir}", level="error")
        return None
    
    results = {}
    
    # 如果指定代码，只读该股票
    if stock_code:
        # 尝试匹配股票目录
        for dir_path in stocks_dir.iterdir():
            if dir_path.is_dir():
                # 检查目录名是否包含代码
                if stock_code in dir_path.name or any(f"{stock_code}*" in p for p in dir_path.glob("*")):
                    note_file = dir_path / "投资笔记.md"
                    if note_file.exists():
                        with open(note_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        results[dir_path.name] = content[:2000]  # 限制长度
                        break
    else:
        # 读取所有股票笔记的frontmatter
        for dir_path in stocks_dir.iterdir():
            if dir_path.is_dir():
                note_file = dir_path / "投资笔记.md"
                if note_file.exists():
                    with open(note_file, 'r', encoding='utf-8') as f:
                        content = f.read(1000)  # 只读frontmatter
                    
                    # 提取frontmatter
                    if content.startswith("---"):
                        end_idx = content.find("---", 3)
                        if end_idx > 0:
                            fm_content = content[3:end_idx].strip()
                            results[dir_path.name] = fm_content
    
    log(f"成功读取 {len(results)} 只股票笔记")
    return results

def main():
    """主函数"""
    log("=" * 60)
    log("DSH 股票数据读取测试")
    log("=" * 60)
    
    # 测试数据读取
    tests = [
        ("每日检查数据", read_daily_check_files),
        ("GF-DMA评分", read_gfdma_data),
        ("投资组合配置", read_stock_portfolio),
        ("投资笔记索引", read_investment_notes),
    ]
    
    results = {}
    for name, func in tests:
        log(f"\n--- 测试: {name} ---")
        try:
            result = func()
            results[name] = result
        except Exception as e:
            log(f"测试失败: {e}", level="error")
            results[name] = {"error": str(e)}
    
    # 输出汇总
    log("\n" + "=" * 60)
    log("测试汇总")
    log("=" * 60)
    
    success_count = sum(1 for v in results.values() if v and "error" not in v)
    log(f"成功: {success_count}/{len(tests)}")
    
    # 输出JSON结果
    print("\n" + json.dumps(results, ensure_ascii=False, indent=2, default=str))
    
    return 0 if success_count == len(tests) else 1

if __name__ == "__main__":
    sys.exit(main())
