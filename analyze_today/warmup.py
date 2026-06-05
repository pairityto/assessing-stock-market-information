import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
from datetime import datetime, timedelta
import time
import contextlib
import io
import os

def warm_up_data(data_path: str = None, is_jump: bool = False):
    """
    提前计算好Alpha因子，并保存到文件中，避免在回测过程中重复计算。
    is_jump: 是否跳过已存在的预热数据，默认为False，即不跳过，重新计算并覆盖已有数据。
    """

    if data_path is None:
        print("数据路径未提供，无法进行预热")


    from alpha import AlphaFactor  # alpha.py 文件中的类名
    alpha = AlphaFactor()

    data_path = Path(data_path)
    processed_dir = data_path / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    data_path = Path(data_path)
    print(f"正在预热数据，输入路径: {data_path}, 输出路径: {processed_dir}, 跳过已存在数据: {is_jump}")

    symbols = list(Path(data_path).glob("*.parquet"))
    # print(f"找到 {len(symbols)} 个数据文件需要预热.")

    for symbol in symbols:
        # print(f"正在预热 {symbol.stem} 的数据...")
        if (Path(data_path) / f"processed/{symbol.stem}.parquet").exists() and is_jump:
            # print(f"{symbol.stem} 的预热数据已存在，跳过.")
            continue

        df = pd.read_parquet(symbol, engine="pyarrow")
        df = alpha.calculate_indicators(df)
        df.to_parquet(processed_dir / f"{symbol.stem}.parquet", index=False)



if __name__ == "__main__":
    warm_up_data(data_path="/Users/mlwang/Documents/Quants/csi300PEstrategy/data/CN_Index/daily/forward/2015-01-01_2026-05-01", is_jump=True)