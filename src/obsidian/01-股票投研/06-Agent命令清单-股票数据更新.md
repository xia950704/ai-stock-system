---
title: 06 Agent命令清单 股票数据更新
tags: [投研, 股票, 数据更新, 配置]
status: active
created: 2026-05-31
updated: 2026-05-31
---

processed: true
processed_date: 2026-09-28

title: "Agent 命令清单 - 股票数据更新"
date: 2026-05-26
tags: [投研, 命令清单, 自动化]
# Agent 命令清单 - 股票数据更新
> **AI 摘要**：股票数据更新自动化命令清单（v1.0），包含25只股票价格批量获取Python脚本、meta.json更新、估值追踪更新等操作流程。目标是通过可执行的agent命令实现股票数据的自动化维护和验证。

---
> 版本: 1.0 | 最后更新: 2026-05-26
> 版本: 1.0 | 最后更新: 2026-05-26
> 目标: 生成可执行的 agent 命令，用于股票数据更新和验证
> 说明: 用户手动执行命令，agent 提供命令清单

---

## 一、每日更新命令

### 1.1 25只股票价格批量获取

```bash
# 获取全部25只股票现价
python3 -c "
import akshare as ak
import pandas as pd
import json

stocks = {
    '港股': ['09926', '01801', '02162', '01177', '01093'],
    'A股主板': ['600276', '603259', '000963', '002262', '002422',
               '600976', '600196', '688506', '688235', '688180', '688366', '603392'],
    '创业板': ['002821', '300759', '300347', '300896', '300122', '300142', '300558'],
    '北交所': ['832566']
}

spot = ak.stock_zh_a_spot_em()
print('=== 25只股票现价 ===')
for category, stock_list in stocks.items():
    print(f'\n【{category}】')
    for code in stock_list:
        match = spot[spot['代码'] == code]
        if len(match) > 0:
            name = match['股票简称'].values[0]
            price = match['最新价'].values[0]
            change = match['涨跌幅'].values[0]
            print(f'{name} {code}: {price} ({change}%)')
        else:
            print(f'{code}: 未找到')
"
```

### 1.2 更新 meta.json 价格

```bash
# 批量更新25只股票的 meta.json 现价
# 先获取最新价格，然后手动更新或运行以下脚本

python3 << 'EOF'
import os
import json
import akshare as ak

vault_base = "/Users/xiashuang/obsidian/all about xia/01-股票投研/股票"
spot = ak.stock_zh_a_spot_em()

stocks = ['600276', '603259', '000963', '002262', '002422',
          '688506', '512400',
          '02162', '01177', '832566', '600976',
          '600196', '300896', '300558', '300759', '300347',
          '002821', '688366', '300122', '603392', '300142',
          '688235', '01801', '688180', '09926', '01093']

# 股票目录映射
stock_dir_map = {
    '600276': '恒瑞医药', '603259': '药明康德', '000963': '华东医药',
    '002262': '恩华药业', '002422': '科伦药业', '688506': '百利天恒', '512400': '512400有色金属ETF',
    '688331': '荣昌生物（观察池/P2）', '02162': '康诺亚',
    '600976': '健民集团', '600196': '复星医药', '300896': '爱美客',
    '300558': '贝达药业', '300759': '康龙化成', '300347': '泰格医药',
    '002821': '凯莱英', '688366': '昊海生科', '300122': '智飞生物',
    '603392': '万泰生物', '300142': '沃森生物', '688235': '百济神州',
    '01801': '信达生物', '688180': '君实生物', '09926': '康方生物',
    '01093': '石药集团'
}

for code in stocks:
    match = spot[spot['代码'] == code]
    if len(match) > 0:
        new_price = float(match['最新价'].values[0])
        dir_name = stock_dir_map.get(code, code)
        meta_path = os.path.join(vault_base, dir_name, "meta.json")
        
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta = json.load(f)
            
            old_price = meta['price_range']['current_price']
            meta['price_range']['current_price'] = new_price
            
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            
            print(f'{code} {dir_name}: {old_price} -> {new_price}')
        else:
            print(f'{code}: meta.json 不存在')
EOF
```

### 1.3 更新估值追踪.md 现价

```bash
# 批量更新25只股票的估值追踪.md 当前价
python3 << 'EOF'
import os
import json
import re
import akshare as ak

vault_base = "/Users/xiashuang/obsidian/all about xia/01-股票投研/股票"
spot = ak.stock_zh_a_spot_em()

stocks = ['600276', '603259', '000963', '002262', '002422',
          '688506', '512400',
          '02162', '01177', '832566', '600976',
          '600196', '300896', '300558', '300759', '300347',
          '002821', '688366', '300122', '603392', '300142',
          '688235', '01801', '688180', '09926', '01093']

stock_dir_map = {
    '600276': '恒瑞医药', '603259': '药明康德', '000963': '华东医药',
   '688331': '荣昌生物（观察池/P2）', '002422': '科伦药业', '02162': '康诺亚',
    '01177': '康哲药业', '832566': '梓橦宫', '688506': '百利天恒',
    '600976': '健民集团', '600196': '复星医药', '300896': '爱美客',
    '300558': '贝达药业', '300759': '康龙化成', '300347': '泰格医药',
    '002821': '凯莱英', '688366': '昊海生科', '300122': '智飞生物',
    '603392': '万泰生物', '300142': '沃森生物', '688235': '百济神州',
    '01801': '信达生物', '688180': '君实生物', '09926': '康方生物',
    '01093': '石药集团'
}

for code in stocks:
    match = spot[spot['代码'] == code]
    if len(match) > 0:
        new_price = float(match['最新价'].values[0])
        dir_name = stock_dir_map.get(code, code)
        val_path = os.path.join(vault_base, dir_name, "估值追踪.md")
        
        if os.path.exists(val_path):
            with open(val_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 替换当前价
            old_price = new_price - 0.01  # 占位，实际用正则匹配
            new_content = re.sub(
                r'当前价.*?¥[\d.]+',
                f'当前价: ¥{new_price:.2f}',
                content
            )
            
            # 也更新表格中的现价
            new_content = re.sub(
                r'\| 股价 \|.*?¥[\d.]+',
                f'| 股价 | ¥{new_price:.2f}',
                new_content
            )
            
            if new_content != content:
                with open(val_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f'{code} {dir_name}: 估值追踪.md 已更新')
EOF
```

---

## 二、每周更新命令

### 2.1 获取重大事件列表

```bash
# 从港交所披露易获取港股公告
# 手动访问: https://www.hkexnews.hk/index_c.htm
# 搜索关键词: BD, 授权, 许可, 临床, 获批, 减持

# 从巨潮资讯获取A股公告
# 手动访问: http://www.cninfo.com.cn
# 搜索股票代码，筛选: 临时公告

# 从CDE官网获取新药审批进展
# 手动访问: https://www.cde.org.cn
# 查询: 新药审批状态

# 从临床登记网站获取试验状态
# 手动访问: https://www.chictr.org.cn (中国)
# 手动访问: https://clinicaltrials.gov (美国)
```

### 2.2 获取券商研报摘要

```bash
# 使用同花顺/iFinD/Wind获取研报
# 手动访问券商官网或终端

# 关键词搜索:
# - 康方生物 研报
# - 信达生物 研报
# - 荣昌生物 研报
# - 百济神州 研报
# - 百利天恒 研报
```

---

## 三、高优先级验证命令

### 3.1 港股验证（5项）

```bash
# 1. 康方生物 - 高管减持后续
# 手动访问: https://www.hkexnews.hk
# 搜索: 09926 权益披露
# 查看: 董事/大股东持股变化

# 2. 康方生物 - Summit依沃西海外进展
# 手动访问: https://www.summittx.com (Summit Therapeutics官网)
# 搜索: Aundem (依沃西海外名称)
# 查看: 临床进展公告

# 3. 信达生物 - 2025年Q1/Q2销售数据
# 手动访问: https://www.hkexnews.hk
# 搜索: 01801 业绩公告
# 查看: 产品收入、销售数据

# 4. 康诺亚 - CM310销售数据
# 手动访问: https://www.hkexnews.hk
# 搜索: 02162 业绩公告
# 查看: 康悦达销售数据

# 5. 康诺亚 - CMG901与AZ合作金额
# 手动访问: https://www.hkexnews.hk
# 搜索: 02162 合作公告
# 查看: 与阿斯利康合作细节
```

### 3.2 A股验证（7项）

```bash
# 1. 百济神州 - 泽布替尼全球销售
# 手动访问: 百济神州官网投资者关系
# 或: https://ir.beigene.com
# 查看: 季度财报销售数据

# 2. 百济神州 - 管理层变动影响
# 手动访问: 巨潮资讯
# 搜索: 688235 总经理变更
# 查看: 公告详情

# 3. 荣昌生物 - ADC销售数据
# 手动访问: 巨潮资讯
# 搜索: 688506 业绩公告
# 查看: 维迪西妥单抗销售

# 4. 百利天恒 - BL-B01D1临床数据
# 手动访问: 巨潮资讯
# 搜索: 688506 临床进展
# 查看: 最新临床数据公告

# 5. 智飞生物 - 财务合规问题
# 手动访问: 深交所官网
# 搜索: 300122 监管函
# 查看: 监管函具体内容

# 6. 药明康德 - 生物安全法案进展
# 手动访问: https://www.congress.gov
# 搜索: S.3558 Biosecure Act
# 查看: 法案最新进展

# 7. 万泰生物 - 九价HPV批签发
# 手动访问: 中国食品药品检定研究院
# 搜索: 万泰生物 九价HPV 批签发
# 查看: 月度批签发数据
```

---

## 四、月度更新命令

### 4.1 获取估值数据（PE/PB/PS）

```bash
# 使用 akshare 获取估值指标
python3 -c "
import akshare as ak
import pandas as pd

stocks = ['600276', '603259', '000963', '002262', '002422',
          '688506', '688235', '688180', '688366', '603392',
          '002821', '300759', '300347', '300896', '300122',
          '300142', '300558']

print('=== A股估值指标 ===')
for code in stocks:
    try:
        # 获取个股财务数据
        stock_info = ak.stock_individual_info_em(symbol=code)
        print(f'\n{code}:')
        print(stock_info.to_string())
    except Exception as e:
        print(f'{code}: 获取失败 - {e}')
"
```

### 4.2 重新生成K线图

```bash
# 批量重新生成25只股票的K线图
python3 << 'EOF'
import akshare as ak
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import os
from datetime import datetime, timedelta

vault_base = "/Users/xiashuang/obsidian/all about xia/01-股票投研/股票"

stocks = {
    '恒瑞医药': '600276', '药明康德': '603259', '华东医药': '000963',
    '荣昌生物': '688331（观察池/P2）', '科伦药业': '002422', '康诺亚': '02162',
    '康哲药业': '01177', '梓橦宫': '832566', '百利天恒': '688506',
    '健民集团': '600976', '复星医药': '600196', '爱美客': '300896',
    '贝达药业': '300558', '康龙化成': '300759', '泰格医药': '300347',
    '凯莱英': '002821', '昊海生科': '688366', '智飞生物': '300122',
    '万泰生物': '603392', '沃森生物': '300142', '百济神州': '688235',
    '信达生物': '01801', '君实生物': '688180', '康方生物': '09926',
    '石药集团': '01093'
}

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei']
plt.rcParams['axes.unicode_minus'] = False

for name, code in stocks.items():
    stock_dir = os.path.join(vault_base, name, "图表")
    os.makedirs(stock_dir, exist_ok=True)
    
    try:
        # 获取全历史数据
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="19900101", end_date="20260526", adjust="qfq")
        
        if len(df) > 0:
            # 全历史K线图
            fig, ax = plt.subplots(figsize=(14, 6))
            ax.plot(df['日期'], df['收盘'], linewidth=0.8, color='#2196F3')
            ax.set_title(f'{name} ({code}) 全历史K线', fontsize=14)
            ax.set_xlabel('日期')
            ax.set_ylabel('股价 (元)')
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            ax.xaxis.set_major_locator(mdates.YearLocator(5))
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig(os.path.join(stock_dir, "full_history_kline.png"), dpi=150, bbox_inches='tight')
            plt.close()
            
            # 近5年蜡烛图
            df_5y = df[df['日期'] >= '2021-05-26'].copy()
            if len(df_5y) > 0:
                fig, ax = plt.subplots(figsize=(14, 6))
                
                # 绘制蜡烛图
                for i, row in df_5y.iterrows():
                    color = '#F44336' if row['收盘'] < row['开盘'] else '#4CAF50'
                    # 影线
                    ax.plot([i, i], [row['低'], row['高']], color=color, linewidth=0.5)
                    # 实体
                    ax.bar(i, abs(row['收盘'] - row['开盘']), bottom=min(row['收盘'], row['开盘']),
                          width=0.6, color=color, edgecolor=color)
                
                ax.set_title(f'{name} ({code}) 近5年日K蜡烛图', fontsize=14)
                ax.set_xlabel('日期')
                ax.set_ylabel('股价 (元)')
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
                ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
                plt.xticks(rotation=45)
                plt.tight_layout()
                plt.savefig(os.path.join(stock_dir, "recent5y_candle.png"), dpi=150, bbox_inches='tight')
                plt.close()
            
            print(f'{name} ({code}): 图表已更新')
        else:
            print(f'{name} ({code}): 无数据')
    except Exception as e:
        print(f'{name} ({code}): 错误 - {e}')

print('\n全部图表更新完成')
EOF
```

---

## 五、季度更新命令

### 5.1 财报数据获取

```bash
# 获取最新财报数据
python3 -c "
import akshare as ak

# 示例：获取恒瑞医药最新财报
stock_financial = ak.stock_financial_report_sina(stock='600276', symbol='利润表')
print(stock_financial.head())

# 资产负债表
stock_balance = ak.stock_financial_report_sina(stock='600276', symbol='资产负债表')
print(stock_balance.head())

# 现金流量表
stock_cashflow = ak.stock_financial_report_sina(stock='600276', symbol='现金流量表')
print(stock_cashflow.head())
"
```

### 5.2 财务指标计算

```bash
# 计算关键财务指标
python3 << 'EOF'
import akshare as ak
import pandas as pd

stocks = ['600276', '603259', '000963', '002262', '002422',
          '688506', '688235', '688180', '688366', '603392',
          '002821', '300759', '300347', '300896', '300122',
          '300142', '300558']

print('=== 财务指标速览 ===')
for code in stocks:
    try:
        # 获取个股信息
        info = ak.stock_individual_info_em(symbol=code)
        
        # 获取财务数据
        financial = ak.stock_financial_report_sina(stock=code, symbol='利润表')
        
        if len(financial) > 0:
            latest = financial.iloc[0]
            print(f'\n{code}:')
            print(f'  营业收入: {latest.get("营业收入(万元)", "N/A")} 万元')
            print(f'  净利润: {latest.get("净利润(万元)", "N/A")} 万元')
            print(f'  毛利率: {latest.get("毛利率(%)", "N/A")}%')
    except Exception as e:
        print(f'{code}: 获取失败 - {e}')
EOF
```

---

## 六、风险信号预警命令

### 6.1 高管减持监控

```bash
# 监控25只股票的高管减持
python3 -c "
import akshare as ak

stocks = ['600276', '603259', '000963', '002262', '002422',
          '688506', '512400',
          '02162', '01177', '832566', '600976',
          '600196', '300896', '300558', '300759', '300347',
          '002821', '688366', '300122', '603392', '300142',
          '688235', '01801', '688180', '09926', '01093']

print('=== 高管增减持监控 ===')
for code in stocks:
    try:
        # 获取股东增减持
        change = ak.stock_individual_fund_flow_rank(indicator='减持')
        # 注意：akshare的减持监控功能有限，建议手动访问巨潮/港交所
        print(f'{code}: 请手动访问巨潮资讯/港交所披露易查询')
    except Exception as e:
        print(f'{code}: 查询失败 - {e}')

print('\n建议手动查询渠道:')
print('- A股: http://www.cninfo.com.cn -> 临时公告 -> 股东增减持')
print('- 港股: https://www.hkexnews.hk -> 权益披露')
"
```

### 6.2 监管函/处罚监控

```bash
# 监控监管函
python3 -c "
stocks_a = ['600276', '603259', '000963', '002262', '002422',
            '600976', '600196', '688506', '688235', '688180',
            '688366', '603392', '002821', '300759', '300347',
            '300896', '300122', '300142', '300558']

print('=== 监管函监控 ===')
print('请手动访问以下渠道查询:')
print('- 深交所: https://www.szse.cn -> 监管措施')
print('- 上交所: https://www.sse.com.cn -> 监管信息公开')
print('- 北交所: https://www.bse.cn -> 监管措施')
print()
print('重点关注股票:')
print('- 智飞生物 (300122): 2026年5月已收深交所监管函')
"
```

---

## 七、MA视角信息收集模板

### 7.1 医院拜访记录模板

```markdown
# 医院拜访记录 - {日期}

## 基本信息
- 医院: {医院名称}
- 科室: {科室名称}
- 拜访对象: {医生姓名/职称}
- 拜访方式: {面对面/电话/学术活动}

## 产品信息

### {产品1名称}
- 进院情况: {已进院/未进院/等待中}
- 处方量: {月处方量估算}
- 医生反馈: {正面/中性/负面}
- 竞品情况: {主要竞品及替代情况}

### {产品2名称}
- 进院情况: {已进院/未进院/等待中}
- 处方量: {月处方量估算}
- 医生反馈: {正面/中性/负面}
- 竞品情况: {主要竞品及替代情况}

## 竞品信息
- {竞品1}: {价格/进院/处方情况}
- {竞品2}: {价格/进院/处方情况}

## 政策影响
- 医保执行: {是否按医保政策执行}
- 集采影响: {如有，具体影响}

## 备注
{其他观察到的信息}
```

### 7.2 学术活动记录模板

```markdown
# 学术活动记录 - {日期}

## 活动信息
- 活动名称: {活动名称}
- 主办方: {主办方}
- 时间地点: {时间/地点}
- 参与医生: {参与医生数量/级别}

## 产品讨论

### {产品名称}
- 讨论热度: {高/中/低}
- 医生关注点: {疗效/安全性/价格/医保}
- 竞品提及: {哪些竞品被提及}
- 处方意向: {医生处方意愿变化}

## 行业趋势
- 政策风向: {观察到的政策讨论}
- 竞品动态: {竞品推广活动}
- 医生偏好变化: {处方习惯变化}

## 备注
{其他观察}
```

---

## 八、执行检查清单

### 每日检查（5分钟）

- [ ] 25只股票现价更新
- [ ] 重大新闻速览（港交所+巨潮+财联社）
- [ ] 风险信号预警（减持/监管/地缘）

### 每周检查（30分钟）

- [ ] 事件检查（BD/临床/获批/减持/财报）
- [ ] 重点股票深度跟踪（2-3只）
- [ ] MA视角信息收集（医院拜访/学术活动）

### 每月检查（1小时）

- [ ] 估值数据更新（PE/PB/PS）
- [ ] K线图重新生成
- [ ] 投资笔记更新

### 每季度检查（2小时）

- [ ] 财报深度分析
- [ ] 配置方案回顾
- [ ] 跟踪池调整

---

## 九、相关笔记

- [[01-股票投研/01-股票分析框架.md|股票分析框架]]
- ~~01-股票投研/03-投资知识精读笔记~~
- [[01-股票投研/09-港股创新药深度分析.md|港股创新药深度分析]]
- ~~[[01-股票投研/08-A股医药深度分析.md|A股医药深度分析]]~~
- ~~[[01-股票投研/05-股票更新清单.md|股票更新清单]]~~
