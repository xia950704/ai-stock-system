#!/usr/bin/env python3
"""
【转发器】→ strategies/ml/pipeline.py
保留此文件保持原有 cron / 习惯不变
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'strategies', 'ml'))
from pipeline import main
if __name__ == '__main__':
    main()