# P3.5 行情管道修复报告

> 生成时间：2026-10-20 16:45

---

## 一、问题诊断

### 1.1 症状
- realtime_prices_YYYYMMDD.json 最后更新停留在 2026-09-23
- stock_ranking.json 的 latest_date 为 2026-09-30（K 线数据来源 duckdb 同期）
- anchor_status.json 虽然 10-19 有 mtime 更新，但缺乏数据日期字段，无法区分文件修改时间与数据所属交易日

### 1.2 根因
| 数据流 | 原因 | 影响 |
|---|---|---|
| fetch_kline_tencent_incremental.py 未运行 | Hermes cron wrapper 调用旧版脚本（硬编码路径），且 kline 更新依赖的人工触发 | duckdb daily_kline 卡在 09-30，导致排名 latest_date=2026-09-30 |
| realtime_prices_.json 生成缺失 | 原脚本只 stdout 打印，不落盘 | 引擎无法读取最新实时价格 |
| anchor_status.json 无数据日期 | 只存 current/anchor/deviation，缺 data_date 字段 | 新鲜度检查只能依赖 mtime（不可靠） |
| update_anchor.py 线上版本硬编码路径 | Hermes cron wrapper 调用硬编码路径版本（旧版无 DATA_ROOT 环境变量支持） | 容器化/迁移时会断 |

---

## 二、修复动作

| 动作 | 文件 | 说明 |
|---|---|---|
| 1. 运行 fetch_kline_tencent_incremental.py | /Users/xiashuang/.hermes/deeppulse/db/astock.duckdb | 写入 495 行增量 K 线，覆盖 10-20 |
| 2. 运行 stock_ranking.py | ~/harness/stock_daily/stock_ranking.json | run_date=2026-10-20, latest_date=2026-10-20 |
| 3. 同步修复后的脚本到线上目录 | ~/harness/stock_daily/update_anchor.py, fetch_realtime.py | 备份旧版到 backup_phase1/p35_pre_sync/，覆盖为支持 DATA_ROOT/STOCK_DAILY_DIR 的版本 |
| 4. 新增 generate_realtime_snapshot.py | ~/harness/stock_daily/realtime_prices_20261020.json | 落盘实时价格快照，供引擎读取 |
| 5. 引擎侧新增数据日期推断与新鲜度门槛 | src/engine/trading_day.py | data_asof_date 优先用 realtime 快照日期；data_staleness_gate 落后>=2 交易日阻断交易类建议 |

---

## 三、验证结果

| 检查项 | 修复前 | 修复后 |
|---|---|---|
| duckdb daily_kline 最新日期 | 2026-09-30 | 2026-10-20 |
| stock_ranking.json run_date | 2026-10-19 | 2026-10-20 |
| stock_ranking.json latest_date (P0) | 2026-09-30 | 2026-10-20 |
| realtime_prices_.json 存在 | 仅 09-23 | 20261020.json |
| anchor_status.json current 价格 | 09-30 收盘价 | 10-20 实时价 (如恒瑞 47.45) |
| 引擎数据新鲜度 | 行情日期 09-30 | 行情日期 2026-10-20，数据新鲜度：正常 |
| 新鲜度门槛逻辑 | 无 | 落后>=2 交易日 -> 交易类建议降级 OBSERVE |

---

## 四、残留风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| Hermes cron wrapper 仍调用旧路径 | wrapper 未改，但脚本内容已同步为新版 | 建议后续将 wrapper 改为调用 workspace 版本或显式 export 环境变量 |
| 无法确认法定节假日 | 交易日判断仅靠周末，节假日无可信来源 | 已在报告中标注 confirmed: false，保守处理 |
| 实时快照生成依赖人工/定时触发 | 目前是 P3.5 手动运行 generate_realtime_snapshot.py | 需写入 wrapper 或 systemd timer（需用户批准） |
| anchor_status.json 仍缺 data_date 字段 | 为保持兼容未改结构，改为 dated snapshot + 新鲜度门槛 | 可在后续版本在每条记录加 data_date |

---

## 五、回滚步骤

cd /Users/xiashuang/harness/stock_daily
cp /Users/xiashuang/harness/backup_phase1/p35_pre_sync/* .
rm /Users/xiashuang/harness/stock_daily/realtime_prices_20261020.json
# 不回滚 duckdb（数据累积无害）；若需回滚 DB，需从 backup 恢复
