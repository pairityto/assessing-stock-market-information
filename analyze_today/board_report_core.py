import datetime as dt
import json
import os
import re
import sys
import time
from io import StringIO
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

try:
    import akshare as ak
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("Missing dependency: akshare") from exc

try:
    from akshare.datasets import get_ths_js
except Exception:  # pragma: no cover
    get_ths_js = None

try:
    import py_mini_racer
except Exception:  # pragma: no cover
    py_mini_racer = None


PROXY_ENV_VARS = [
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
]
CONFIG_PATH = Path("board_report_config.json")
OUTPUT_DIR = Path("board_report_output")
SUPPORTED_PROVIDERS = ("akshare", "eastmoney", "ths")
SUPPORTED_SCOPES = ("industry", "concept")


def default_config() -> Dict[str, Any]:
    return {
        "meta": {
            "provider": "eastmoney",
            "lookback": 20,
            "topn": 12,
            "sleep": 0.15,
            "last_refresh_at": None,
            "description": (
                "Interactive board report config. "
                "eastmoney uses AkShare Eastmoney endpoints, "
                "akshare uses AkShare wrappers, ths uses Tonghuashun endpoints."
            ),
        },
        "scopes": {
            scope: {
                "display_name": scope.title(),
                "selected_names": [],
                "board_catalog": [],
            }
            for scope in SUPPORTED_SCOPES
        },
    }


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    if not path.exists():
        cfg = default_config()
        save_config(cfg, path)
        return cfg
    payload = json.loads(path.read_text(encoding="utf-8"))
    cfg = default_config()
    cfg["meta"].update(payload.get("meta", {}))
    for scope in SUPPORTED_SCOPES:
        incoming = payload.get("scopes", {}).get(scope, {})
        cfg["scopes"][scope].update(incoming)
    return cfg


def save_config(config: Dict[str, Any], path: Path = CONFIG_PATH) -> None:
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def today_str() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def display_date() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def safe_float(value: Any) -> float:
    if value is None:
        return np.nan
    if isinstance(value, (int, float, np.number)):
        return float(value)
    text = str(value).strip()
    if text in {"", "-", "--", "nan", "None"}:
        return np.nan
    text = text.replace(",", "").replace("%", "")
    multiplier = 1.0
    if text.endswith("万"):
        multiplier = 1e4
        text = text[:-1]
    elif text.endswith("亿"):
        multiplier = 1e8
        text = text[:-1]
    try:
        return float(text) * multiplier
    except Exception:
        return np.nan


def normalize_name(value: str) -> str:
    text = str(value).lower()
    return re.sub(r"[\s\-/（）()_]+", "", text)


def pct_change(first: float, last: float) -> float:
    if not np.isfinite(first) or not np.isfinite(last) or first == 0:
        return np.nan
    return (last / first - 1.0) * 100.0


def sanitize_proxy_env(force_disable: bool = False) -> List[str]:
    removed: List[str] = []
    for key in PROXY_ENV_VARS:
        value = os.environ.get(key)
        if not value:
            continue
        low = str(value).strip().lower()
        if force_disable or "127.0.0.1:9" in low or "localhost:9" in low or "0.0.0.0:9" in low:
            removed.append(f"{key}={value}")
            os.environ.pop(key, None)
    return removed


def retry(func, *args, retries: int = 3, sleep: float = 1.0, **kwargs):
    last_exc = None
    for idx in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover
            last_exc = exc
            if idx < retries - 1:
                time.sleep(sleep * (idx + 1))
    raise last_exc


def get_ths_hexin_v() -> str:
    if py_mini_racer is None or get_ths_js is None:
        raise RuntimeError("ths provider needs py_mini_racer and akshare.datasets.get_ths_js")
    js_path = Path(get_ths_js("ths.js"))
    ctx = py_mini_racer.MiniRacer()
    ctx.eval(js_path.read_text(encoding="utf-8"))
    return ctx.call("v")


def get_ths_headers(kind: str) -> Dict[str, str]:
    route = "gnzjl" if kind == "concept" else "hyzjl"
    return {
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Host": "data.10jqka.com.cn",
        "Referer": f"http://data.10jqka.com.cn/funds/{route}/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "hexin-v": get_ths_hexin_v(),
    }


def _rename_first_matching(df: pd.DataFrame, target: str, keywords: Iterable[str]) -> pd.DataFrame:
    if target in df.columns:
        return df
    for column in df.columns:
        if any(keyword in str(column) for keyword in keywords):
            return df.rename(columns={column: target})
    return df


def _fetch_board_universe_em() -> pd.DataFrame:
    concept = retry(ak.stock_board_concept_name_em).copy()
    industry = retry(ak.stock_board_industry_name_em).copy()
    concept["board_type"] = "concept"
    industry["board_type"] = "industry"
    concept = _rename_first_matching(concept, "板块名称", ["名称"])
    industry = _rename_first_matching(industry, "板块名称", ["名称"])
    concept = _rename_first_matching(concept, "板块代码", ["代码"])
    industry = _rename_first_matching(industry, "板块代码", ["代码"])
    universe = pd.concat([concept, industry], ignore_index=True, sort=False)
    universe = universe.dropna(subset=["板块名称"]).drop_duplicates(subset=["板块名称", "board_type"])
    universe["板块名称"] = universe["板块名称"].astype(str)
    universe["板块代码"] = universe.get("板块代码", "").astype(str)
    universe["norm"] = universe["板块名称"].map(normalize_name)
    return universe


def _fetch_board_universe_ths() -> pd.DataFrame:
    concept = retry(ak.stock_board_concept_name_ths).copy()
    industry = retry(ak.stock_board_industry_name_ths).copy()
    concept = concept.rename(columns={"name": "板块名称", "code": "板块代码"})
    industry = industry.rename(columns={"name": "板块名称", "code": "板块代码"})
    concept["board_type"] = "concept"
    industry["board_type"] = "industry"
    universe = pd.concat([concept, industry], ignore_index=True, sort=False)
    universe = universe.dropna(subset=["板块名称"]).drop_duplicates(subset=["板块名称", "board_type"])
    universe["板块名称"] = universe["板块名称"].astype(str)
    universe["板块代码"] = universe["板块代码"].astype(str)
    universe["norm"] = universe["板块名称"].map(normalize_name)
    return universe


def fetch_board_universe(provider: str) -> pd.DataFrame:
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}")
    if provider in {"akshare", "eastmoney"}:
        return _fetch_board_universe_em()
    return _fetch_board_universe_ths()


def _fetch_fund_flow_em() -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for sector_type in ["概念资金流", "行业资金流"]:
        for period in ["今日", "5日", "10日"]:
            df = retry(ak.stock_sector_fund_flow_rank, indicator=period, sector_type=sector_type).copy()
            df = _rename_first_matching(df, "板块名称", ["名称"])
            df["sector_type"] = sector_type
            df["period"] = period
            frames.append(df)
    flow = pd.concat(frames, ignore_index=True, sort=False)
    flow["norm"] = flow["板块名称"].astype(str).map(normalize_name)
    return flow


def _fetch_fund_flow_ths_one(kind: str, period: str) -> pd.DataFrame:
    route = "gnzjl" if kind == "concept" else "hyzjl"
    board_part = "" if period == "今日" else f"board/{period[:-1]}/"
    url = f"http://data.10jqka.com.cn/funds/{route}/{board_part}field/tradezdf/order/desc/page/1/ajax/1/free/1/"
    response = requests.get(url, headers=get_ths_headers(kind), timeout=20)
    tables = pd.read_html(StringIO(response.text))
    if not tables:
        raise RuntimeError(f"THS fund flow page has no table: {url}")
    df = tables[0].copy()
    df = df.rename(
        columns={
            "行业": "板块名称",
            "涨跌幅": "板块涨跌幅",
            "阶段涨跌幅": "板块涨跌幅",
            "净额(亿)": "主力净流入-净额",
        }
    )
    if "板块名称" not in df.columns:
        raise RuntimeError(f"THS flow columns unexpected: {list(df.columns)}")
    if "主力净流入-净额" in df.columns:
        df["主力净流入-净额"] = df["主力净流入-净额"].map(safe_float) * 1e8
    if "板块涨跌幅" in df.columns:
        df["板块涨跌幅"] = df["板块涨跌幅"].map(safe_float)
    df["sector_type"] = "概念资金流" if kind == "concept" else "行业资金流"
    df["period"] = period
    df["norm"] = df["板块名称"].astype(str).map(normalize_name)
    return df


def _fetch_fund_flow_ths() -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for kind in ["concept", "industry"]:
        for period in ["今日", "5日", "10日"]:
            frames.append(_fetch_fund_flow_ths_one(kind, period))
    return pd.concat(frames, ignore_index=True, sort=False)


def fetch_fund_flow(provider: str) -> pd.DataFrame:
    if provider in {"akshare", "eastmoney"}:
        return _fetch_fund_flow_em()
    if provider == "ths":
        return _fetch_fund_flow_ths()
    raise ValueError(f"Unsupported provider: {provider}")


def _get_history_em(board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
    if board_type == "concept":
        df = retry(ak.stock_board_concept_hist_em, symbol=board_name, start_date=start_date, end_date=end_date, period="日k", adjust="")
    else:
        df = retry(ak.stock_board_industry_hist_em, symbol=board_name, start_date=start_date, end_date=end_date, period="日k", adjust="")
    df = df.copy()
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期")
    for column in ["收盘", "涨跌幅", "成交额", "换手率"]:
        if column in df.columns:
            df[column] = df[column].map(safe_float)
    return df


def _get_history_ths(board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
    fn = ak.stock_board_concept_index_ths if board_type == "concept" else ak.stock_board_industry_index_ths
    df = retry(fn, symbol=board_name, start_date=start_date, end_date=end_date).copy()
    df = df.rename(
        columns={
            "开盘价": "开盘",
            "最高价": "最高",
            "最低价": "最低",
            "收盘价": "收盘",
            "成交量": "成交量",
            "成交额": "成交额",
        }
    )
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期")
    for column in ["收盘", "成交额"]:
        if column in df.columns:
            df[column] = df[column].map(safe_float)
    if "收盘" in df.columns and "涨跌幅" not in df.columns:
        df["涨跌幅"] = df["收盘"].pct_change() * 100
    return df


def get_history(board_name: str, board_type: str, start_date: str, end_date: str, provider: str) -> pd.DataFrame:
    if provider in {"akshare", "eastmoney"}:
        return _get_history_em(board_name, board_type, start_date, end_date)
    if provider == "ths":
        return _get_history_ths(board_name, board_type, start_date, end_date)
    raise ValueError(f"Unsupported provider: {provider}")


def refresh_catalog(config: Dict[str, Any], provider: Optional[str] = None) -> Dict[str, Any]:
    cfg = json.loads(json.dumps(config))
    provider = provider or cfg["meta"].get("provider", "eastmoney")
    universe = fetch_board_universe(provider)
    for scope in SUPPORTED_SCOPES:
        scope_df = universe[universe["board_type"] == scope].copy()
        existing_selected = set(cfg["scopes"][scope].get("selected_names", []))
        catalog = []
        for _, row in scope_df.sort_values("板块名称").iterrows():
            board_name = str(row["板块名称"])
            catalog.append(
                {
                    "board_name": board_name,
                    "board_code": str(row.get("板块代码", "") or ""),
                    "board_type": scope,
                    "selected": board_name in existing_selected,
                }
            )
        cfg["scopes"][scope]["board_catalog"] = catalog
        cfg["scopes"][scope]["selected_names"] = [item["board_name"] for item in catalog if item["selected"]]
    cfg["meta"]["provider"] = provider
    cfg["meta"]["last_refresh_at"] = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return cfg


def set_scope_selection(config: Dict[str, Any], scope: str, selected_names: List[str]) -> Dict[str, Any]:
    cfg = json.loads(json.dumps(config))
    selected_set = set(selected_names)
    cfg["scopes"][scope]["selected_names"] = list(selected_names)
    catalog = cfg["scopes"][scope].get("board_catalog", [])
    for item in catalog:
        item["selected"] = item.get("board_name") in selected_set
    return cfg


def selected_boards(config: Dict[str, Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for scope in SUPPORTED_SCOPES:
        for item in config["scopes"][scope].get("board_catalog", []):
            if item.get("selected"):
                rows.append(
                    {
                        "board_name": str(item.get("board_name", "")),
                        "board_code": str(item.get("board_code", "")),
                        "board_type": scope,
                    }
                )
    return rows


def _find_flow_row(flow: pd.DataFrame, board_name: str, period: str) -> Optional[pd.Series]:
    if flow.empty:
        return None
    norm = normalize_name(board_name)
    exact = flow[(flow.get("period") == period) & (flow.get("norm") == norm)]
    if not exact.empty:
        return exact.iloc[0]
    contain = flow[(flow.get("period") == period) & (flow["norm"].astype(str).str.contains(norm, regex=False, na=False))]
    return None if contain.empty else contain.iloc[0]


def _flow_value(row: Optional[pd.Series], key_contains: str) -> float:
    if row is None:
        return np.nan
    for column in row.index:
        if key_contains in str(column):
            return safe_float(row[column])
    return np.nan


def label_board(pct1: float, pct5: float, pct20: float, flow_today: float, flow5: float, vol_ratio: float) -> str:
    p1 = pct1 if np.isfinite(pct1) else 0.0
    p5 = pct5 if np.isfinite(pct5) else 0.0
    p20 = pct20 if np.isfinite(pct20) else 0.0
    ft = flow_today if np.isfinite(flow_today) else 0.0
    f5 = flow5 if np.isfinite(flow5) else 0.0
    vr = vol_ratio if np.isfinite(vol_ratio) else 1.0
    if p20 >= 20 and ft < 0:
        return "高位分歧"
    if p20 >= 20 and ft >= 0:
        return "高位强趋势"
    if p5 >= 8 and ft > 0:
        return "短线加速"
    if p20 <= 10 and p5 >= 2 and ft > 0 and vr >= 1.1:
        return "低位启动"
    if p20 <= 6 and f5 > 0:
        return "低位吸金"
    if p20 <= 5 and p1 > 0:
        return "低位异动"
    if ft < 0 and f5 < 0:
        return "资金流出"
    if p20 < 0:
        return "低位观察"
    return "中性轮动"


def score_board(pct1: float, pct5: float, pct20: float, flow_ratio: float, vol_ratio: float) -> float:
    vals = [
        np.nan_to_num(pct1, nan=0.0) * 0.20,
        np.nan_to_num(pct5, nan=0.0) * 0.35,
        np.nan_to_num(pct20, nan=0.0) * 0.20,
        np.nan_to_num(flow_ratio, nan=0.0) * 0.20,
        (np.nan_to_num(vol_ratio, nan=1.0) - 1.0) * 5.0,
    ]
    return float(sum(vals))


def analyze_selected_boards(config: Dict[str, Any]) -> pd.DataFrame:
    provider = config["meta"].get("provider", "eastmoney")
    lookback = int(config["meta"].get("lookback", 20))
    pause = float(config["meta"].get("sleep", 0.15))
    boards = selected_boards(config)
    flow = fetch_fund_flow(provider)
    end = dt.datetime.now().strftime("%Y%m%d")
    start = (dt.datetime.now() - dt.timedelta(days=max(80, lookback * 4))).strftime("%Y%m%d")
    rows: List[Dict[str, Any]] = []

    for item in boards:
        board_name = item["board_name"]
        scope = item["board_type"]
        try:
            hist = get_history(board_name, scope, start, end, provider)
            if hist.empty or "收盘" not in hist.columns:
                raise RuntimeError("history is empty")
            hist = hist.tail(max(lookback + 1, 21)).copy()
            close = hist["收盘"].astype(float).values
            pct1 = safe_float(hist.iloc[-1].get("涨跌幅", np.nan)) if "涨跌幅" in hist.columns else pct_change(close[-2], close[-1])
            pct5 = pct_change(close[-6], close[-1]) if len(close) >= 6 else pct_change(close[0], close[-1])
            pct20 = pct_change(close[-21], close[-1]) if len(close) >= 21 else pct_change(close[0], close[-1])
            if "成交额" in hist.columns and hist["成交额"].notna().sum() >= 5:
                last_amt = float(hist["成交额"].iloc[-1])
                median_amt = float(hist["成交额"].iloc[:-1].tail(20).median())
                vol_ratio = last_amt / median_amt if median_amt > 0 else np.nan
            else:
                vol_ratio = np.nan
            close_latest = float(close[-1])
        except Exception as exc:
            print(f"[WARN] history failed for {board_name}: {exc}", file=sys.stderr)
            pct1 = pct5 = pct20 = vol_ratio = close_latest = np.nan

        flow_today = _find_flow_row(flow, board_name, "今日")
        flow_5 = _find_flow_row(flow, board_name, "5日")
        flow_10 = _find_flow_row(flow, board_name, "10日")
        main_today = _flow_value(flow_today, "主力净流入-净额")
        main_ratio_today = _flow_value(flow_today, "主力净流入-净占比")
        main_5 = _flow_value(flow_5, "主力净流入-净额")
        main_10 = _flow_value(flow_10, "主力净流入-净额")
        label = label_board(pct1, pct5, pct20, main_today, main_5, vol_ratio)
        score = score_board(pct1, pct5, pct20, main_ratio_today, vol_ratio)
        rows.append(
            {
                "date": display_date(),
                "provider": provider,
                "board_type": scope,
                "board_name": board_name,
                "board_code": item.get("board_code", ""),
                "close": close_latest,
                "pct_1d": pct1,
                "pct_5d": pct5,
                "pct_20d": pct20,
                "volume_ratio": vol_ratio,
                "main_net_inflow_today": main_today,
                "main_net_ratio_today": main_ratio_today,
                "main_net_inflow_5d": main_5,
                "main_net_inflow_10d": main_10,
                "score": score,
                "label": label,
            }
        )
        time.sleep(pause)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["score", "pct_20d"], ascending=[False, False], na_position="last").reset_index(drop=True)
    return df


def _fmt_pct(value: Any) -> str:
    return "NA" if not np.isfinite(safe_float(value)) else f"{safe_float(value):+.2f}%"


def _fmt_num(value: Any, digits: int = 2) -> str:
    return "NA" if not np.isfinite(safe_float(value)) else f"{safe_float(value):.{digits}f}"


def _fmt_money(value: Any) -> str:
    x = safe_float(value)
    if not np.isfinite(x):
        return "NA"
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e8:
        return f"{sign}{x / 1e8:.2f}亿"
    if x >= 1e4:
        return f"{sign}{x / 1e4:.2f}万"
    return f"{sign}{x:.0f}"


def render_html_report(df: pd.DataFrame, config: Dict[str, Any], path: Path) -> None:
    topn = int(config["meta"].get("topn", 12))

    def section(title: str, frame: pd.DataFrame) -> str:
        view = frame.head(topn).copy()
        if view.empty:
            return f"<h2>{title}</h2><p>No data.</p>"
        formatters = {
            "pct_1d": _fmt_pct,
            "pct_5d": _fmt_pct,
            "pct_20d": _fmt_pct,
            "volume_ratio": _fmt_num,
            "main_net_inflow_today": _fmt_money,
            "main_net_ratio_today": _fmt_pct,
            "main_net_inflow_5d": _fmt_money,
            "main_net_inflow_10d": _fmt_money,
            "score": _fmt_num,
            "close": _fmt_num,
        }
        return f"<h2>{title}</h2>{view.to_html(index=False, border=0, formatters=formatters, classes='report-table')}"

    combined = df.copy()
    industry = df[df["board_type"] == "industry"].copy()
    concept = df[df["board_type"] == "concept"].copy()

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>Board Daily Report</title>
  <style>
    body {{ font-family: "Microsoft YaHei UI", Arial, sans-serif; margin: 24px; background: #f6f8fb; color: #1f2937; }}
    h1 {{ margin-bottom: 8px; }}
    .meta {{ margin-bottom: 20px; color: #4b5563; }}
    .report-table {{ border-collapse: collapse; width: 100%; background: white; margin-bottom: 24px; }}
    .report-table th, .report-table td {{ border: 1px solid #d1d5db; padding: 8px 10px; font-size: 13px; }}
    .report-table th {{ background: #e5eefb; position: sticky; top: 0; }}
    .report-table tr:nth-child(even) {{ background: #f9fafb; }}
  </style>
</head>
<body>
  <h1>概念/板块日报</h1>
  <div class="meta">
    日期: {display_date()}<br>
    数据源: {config["meta"].get("provider", "eastmoney")}<br>
    统计窗口: {config["meta"].get("lookback", 20)} 个交易日
  </div>
  {section("总表", combined)}
  {section("行业板块", industry)}
  {section("概念板块", concept)}
</body>
</html>"""
    path.write_text(html, encoding="utf-8")


def save_report_outputs(df: pd.DataFrame, config: Dict[str, Any], out_dir: Path = OUTPUT_DIR) -> Dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = today_str()
    csv_path = out_dir / f"board_report_{stamp}.csv"
    html_path = out_dir / f"board_report_{stamp}.html"
    config_path = out_dir / f"board_report_config_snapshot_{stamp}.json"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    render_html_report(df, config, html_path)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"csv": csv_path, "html": html_path, "config": config_path}
