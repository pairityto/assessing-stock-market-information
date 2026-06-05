#!/usr/bin/env python
"""
诊断脚本：检查买入日期和价格的跟踪。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from strategy import LowPEstrategy

# 测试第一天
print("=== Testing first day ===")
date1 = "2020-01-03"
data_path = "data/CN_Index/daily/forward/2016-01-01_2026-01-01/processed"

# 读取前100只股票作为股票池
df = pd.read_parquet(Path(data_path) / "000001.parquet", columns=["date"])
available_dates = df[df["date"] <= date1]["date"].max()
print(f"Latest available date before {date1}: {available_dates}")

# 获取所有可用的股票文件
all_symbols = [f.stem for f in Path(data_path).glob("*.parquet")]
print(f"Total symbols in data: {len(all_symbols)}")

# 创建策略实例
strategy = LowPEstrategy(
    date=date1,
    data_path=data_path,
    cash=100_000,
    stock_pool=all_symbols[:100],  # 只用前100只
    max_hold_days=5,
    max_stock_num=3,
)

print(f"Initial buy_dates: {strategy.buy_dates}")
print(f"Initial buy_prices: {strategy.buy_prices}")

# 执行选股和购买
try:
    (total_value, cash, assets, order_history), history_recommend = strategy.run_today()
    print(f"\nAfter run_today:")
    print(f"  Total value: {total_value}")
    print(f"  Cash: {cash}")
    print(f"  Positions: {len(assets)}")
    print(f"  Assets:\n{assets}")
    print(f"  buy_dates: {strategy.buy_dates}")
    print(f"  buy_prices: {strategy.buy_prices}")
    if not order_history.empty:
        print(f"  Orders:\n{order_history}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
