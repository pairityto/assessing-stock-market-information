import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from get_data import GetData, save_csi300_data
from strategy import LowPEstrategy
from warmup import warm_up_data


DEFAULT_CONFIG: Dict[str, Any] = {
    "global": {
        "end_date": "",
        "lookback_days_for_download": 500,
        "sample_size": 10000,
        "top_n": 10,
        "strategy": {
            "lookback_days": 252,
            "percentile": 0.2,
            "max_hold_days": 90,
            "stop_profit": 0.25,
            "random_select": False,
        },
    },
    "sectors": [
        {
            "name": "CSI300-A",
            "components_csv": "data/CSI300_components.csv",
            "symbol_column": "TickFlow代码",
            "data_root": "data/CSI300_A",
            "auto_fetch_csi300_if_missing": True,
            "enabled": True,
        },
        {
            "name": "CSI300-B",
            "components_csv": "data/CSI300_components.csv",
            "symbol_column": "TickFlow代码",
            "data_root": "data/CSI300_B",
            "auto_fetch_csi300_if_missing": True,
            "enabled": True,
        },
    ],
}

DEFAULT_CONFIG_PATH = Path("dual_sector_config.json")


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Dict[str, Any]:
    if not config_path.exists():
        save_config(DEFAULT_CONFIG, config_path)
        return deepcopy(DEFAULT_CONFIG)

    with config_path.open("r", encoding="utf-8") as fh:
        loaded = json.load(fh)

    config = deepcopy(DEFAULT_CONFIG)
    config["global"].update(loaded.get("global", {}))
    loaded_sectors = loaded.get("sectors", [])
    if loaded_sectors:
        config["sectors"] = []
        for idx, sector in enumerate(loaded_sectors):
            base = deepcopy(DEFAULT_CONFIG["sectors"][idx % len(DEFAULT_CONFIG["sectors"])])
            base.update(sector)
            config["sectors"].append(base)
    return config


def save_config(config: Dict[str, Any], config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def resolve_dates(global_config: Dict[str, Any]) -> Dict[str, str]:
    end_date = global_config.get("end_date") or datetime.now().strftime("%Y-%m-%d")
    start_date = (
        datetime.strptime(end_date, "%Y-%m-%d")
        - timedelta(days=int(global_config.get("lookback_days_for_download", 500)))
    ).strftime("%Y-%m-%d")
    return {"start_date": start_date, "end_date": end_date}


def load_sector_symbols(sector: Dict[str, Any]) -> List[str]:
    csv_path = Path(sector["components_csv"])
    if not csv_path.exists() and sector.get("auto_fetch_csi300_if_missing"):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        save_csi300_data(str(csv_path))

    if not csv_path.exists():
        raise FileNotFoundError(f"板块成分股文件不存在: {csv_path}")

    df = pd.read_csv(csv_path)
    symbol_column = sector.get("symbol_column", "symbol")
    if symbol_column not in df.columns:
        fallback_columns = ["TickFlow代码", "symbol", "stock_code", "代码", "证券代码"]
        for column in fallback_columns:
            if column in df.columns:
                symbol_column = column
                break
        else:
            raise ValueError(f"{csv_path} 中找不到股票代码列: {sector.get('symbol_column')}")

    symbols = (
        df[symbol_column]
        .dropna()
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .tolist()
    )
    if not symbols:
        raise ValueError(f"{csv_path} 中没有可用股票代码")
    return symbols


def run_sector_analysis(sector: Dict[str, Any], global_config: Dict[str, Any]) -> pd.DataFrame:
    dates = resolve_dates(global_config)
    start_date = dates["start_date"]
    end_date = dates["end_date"]

    symbols = load_sector_symbols(sector)
    data_root = Path(sector["data_root"])
    getdata = GetData(start_date=start_date, end_date=end_date, data_dir=data_root)
    getdata.batch_download_tickflow(symbols=symbols)

    daily_dir = data_root / "daily" / "forward" / f"{start_date}_{end_date}"
    warm_up_data(str(daily_dir), is_jump=True)

    processed_dir = daily_dir / "processed"
    available_symbols = [p.stem for p in processed_dir.glob("*.parquet")]
    if not available_symbols:
        raise ValueError(f"{sector['name']} 没有可用的预热数据: {processed_dir}")

    sample_size = min(int(global_config.get("sample_size", 10000)), len(available_symbols))
    rng = np.random.default_rng()
    stock_pool = rng.choice(available_symbols, size=sample_size, replace=False).tolist()

    top_n = int(global_config.get("top_n", 10))
    strategy_config = global_config.get("strategy", {})
    strategy = LowPEstrategy(
        date=end_date,
        data_path=processed_dir,
        stock_pool=stock_pool,
        lookback_days=int(strategy_config.get("lookback_days", 252)),
        percentile=float(strategy_config.get("percentile", 0.2)),
        max_hold_days=int(strategy_config.get("max_hold_days", 90)),
        max_stock_num=top_n,
        max_weight=1 / top_n,
        stop_profit=float(strategy_config.get("stop_profit", 0.25)),
        random_select=bool(strategy_config.get("random_select", False)),
    )

    recommended = strategy.get_recommend().copy()
    recommended.insert(0, "sector", sector["name"])
    recommended.insert(0, "date", end_date)

    output_dir = data_root
    output_dir.mkdir(parents=True, exist_ok=True)
    daily_output = output_dir / f"recommended_stocks_{end_date}.csv"
    recommended.to_csv(daily_output, index=False, encoding="utf-8-sig")
    return recommended


def run_dual_sector_report(config_path: Path = DEFAULT_CONFIG_PATH) -> pd.DataFrame:
    config = load_config(config_path)
    frames: List[pd.DataFrame] = []
    for sector in config["sectors"]:
        if not sector.get("enabled", True):
            continue
        frames.append(run_sector_analysis(sector, config["global"]))

    if not frames:
        raise ValueError("没有启用任何板块")

    combined = pd.concat(frames, ignore_index=True)
    report_dir = Path("data") / "dual_sector_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_date = resolve_dates(config["global"])["end_date"]
    combined.to_csv(report_dir / f"dual_sector_report_{report_date}.csv", index=False, encoding="utf-8-sig")
    return combined


if __name__ == "__main__":
    report = run_dual_sector_report()
    print(report.to_string(index=False, max_rows=None, max_cols=None))
