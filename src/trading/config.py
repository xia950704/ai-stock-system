"""
统一配置中心
==============
所有策略共享的参数集中管理。
修改配置只需改这里，不用逐个文件找。
"""
import os

# ==================== 项目路径 ====================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(PROJECT_ROOT, 'logs')
REPORTS_DIR = os.path.join(PROJECT_ROOT, 'reports')

# ==================== 资金管理 ====================
INITIAL_CAPITAL = 20000.0              # 初始资金 ¥20,000
COMMISSION_RATE = 0.0003               # 佣金万三
SLIPPAGE = 0.001                       # 滑点 0.1%
POSITION_RATIO = 0.95                  # 每次仓位 95%
STOP_LOSS = -0.05                      # 单笔止损 -5%
TAKE_PROFIT = 0.08                     # 单笔止盈 +8%

# ==================== ML 策略参数 ====================
ML_SIGNAL_THRESHOLD = 0.55
ML_N_ESTIMATORS = 100
ML_MAX_DEPTH = 6
ML_MIN_SAMPLES_SPLIT = 20
ML_MODEL_DIR = os.path.join(PROJECT_ROOT, 'models')

# ==================== 配对交易参数 ====================
PAIRS_Z_ENTRY = 2.0                    # 开仓阈值 |z| > 2
PAIRS_Z_EXIT = 0.5                     # 平仓阈值 |z| < 0.5
PAIRS_Z_WINDOW = 30                    # z-score 滚动窗口（交易日）

# ==================== 数据参数 ====================
DATA_API_DELAY = 0.3                   # API请求间隔（秒）
MIN_DATA_DAYS = 60                     # 最少需要的交易日数

# ==================== 定时任务 ====================
CRON_LOG_DIR = LOGS_DIR

# 确保日志目录存在
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)