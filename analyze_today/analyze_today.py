import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import time
import akshare as ak
from tickflow import TickFlow
import contextlib
import io
import os

from warmup import warm_up_data
from get_data import GetData, save_csi300_data

tf = TickFlow(api_key="tk_80cbdb5edac24017b3481dccbc41c428")

# Part 1: 获取 CSI300 往前一年的数据

#利用 akshare 获取 CSI300 成分股数据，并保存到本地 CSV 文件中
#如果akshrae的接口失效了，就让ai改成用本地文件吧
#这个函数不能频繁运行，因为是个爬虫，容易被ban
is_update_csi300 = False  # 是否更新 CSI300 成分股数据，默认为 False，即不更新，直接使用本地数据
if not Path('data/CSI300_components.csv').exists() or is_update_csi300:
    save_csi300_data('data/CSI300_components.csv')
else:
    print("CSI300成分股数据已存在，跳过下载.")
    df = pd.read_csv('data/CSI300_components.csv')
    symbols = df['TickFlow代码'].tolist()
    print(f"已加载 {len(symbols)} 只股票的CSI300成分股数据.")


# 
today = datetime.now().strftime('%Y-%m-%d')
#获取今天往前365天的日期
start_date = (datetime.now() - timedelta(days=500)).strftime('%Y-%m-%d')

data_root = Path('data/CSI300')

getdata = GetData(start_date=start_date, end_date=today, data_dir=data_root)
getdata.batch_download_tickflow(symbols=symbols)
#预热数据
warm_up_data(f'{data_root}/daily/forward/{start_date}_{today}', is_jump=True)

# Part 2: 根据今天的数据，获取推荐的股票列表，并保存到本地

# 初始化 strategy 类

from strategy import LowPEstrategy
import numpy as np

processed_dir = Path(data_root / f"daily/forward/{start_date}_{today}/processed")

symbols = [p.stem for p in processed_dir.glob("*.parquet")]
# 不固定 seed：每次运行都抽取不同股票池，适合需要随机性的回测
rng = np.random.default_rng()
stock_pool = rng.choice(symbols, size=min(10_000, len(symbols)), replace=False)
print(f"Total available symbols: {len(stock_pool)}")

n = 10  # 推荐的股票数量，可以根据需要调整

strategy = LowPEstrategy(date=today, 
                         data_path=processed_dir,
                         stock_pool=stock_pool,
                         # 策略参数（可按需调整）
                         lookback_days=252,
                         percentile=0.2,
                         max_hold_days=90,
                         max_stock_num=n,
                         max_weight=1/n, #depends on max_stock_num, should be <= 1/max_stock_num
                         stop_profit=0.25,
                         random_select=False,
                         )

recommended_stocks = strategy.get_recommend()

print(recommended_stocks.to_string(index=False, max_rows=None, max_cols=None))

output_dir = Path("data/CSI300")
output_dir.mkdir(parents=True, exist_ok=True)

recommended_with_date = recommended_stocks.copy()
if "date" in recommended_with_date.columns:
    recommended_with_date["date"] = today
else:
    recommended_with_date.insert(0, "date", today)

output_file = output_dir / "recommend_stocks.csv"
recommended_with_date.to_csv(output_file, mode="a", header=not output_file.exists(), index=False, encoding="utf-8-sig")

full_list_file = output_dir / f"recommended_stocks_{today}.csv"
recommended_with_date.to_csv(full_list_file, index=False, encoding="utf-8-sig")

print(f"推荐股票已保存到: {full_list_file}")
