#!/usr/bin/env python3
"""
【转发器】→ strategies/pairs/runner.py
保留此文件保持原有 cron / 习惯不变
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'strategies', 'pairs'))
from runner import main
if __name__ == '__main__':
    main()