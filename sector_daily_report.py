#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股板块景气度与资金流日报

功能：
1. 自动抓取东方财富口径的行业/概念板块资金流排名；
2. 对指定科技板块做近 1/5/20 个交易日涨跌幅、成交额放量、主力资金流统计；
3. 生成 Markdown 日报和 CSV 明细；
4. 按短线口径给出：已明显拉升、低位启动、滞涨观察、资金流出/退潮等标签。

依赖：
    pip install -U akshare pandas numpy requests tqdm

运行：
    python sector_daily_report.py
    python sector_daily_report.py --out ./reports --lookback 20 --topn 12

建议运行时间：A股收盘后 15:30 以后，或晚间复盘时。

注意：
- 本脚本只做数据归纳，不构成投资建议。
- AKShare/东方财富接口偶尔会因网络或页面调整失败，脚本已做容错，但仍建议检查日志。
"""

from __future__ import annotations

import argparse
import datetime as dt
import difflib
import inspect
import math
import os
import re
import sys
import time
from io import StringIO
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import board_config

try:
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    BeautifulSoup = None

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


def _looks_like_dead_local_proxy(value: str) -> bool:
    s = str(value).strip().lower()
    return any(token in s for token in ["127.0.0.1:9", "localhost:9", "0.0.0.0:9"])


def sanitize_proxy_env(force_disable: bool = False) -> List[str]:
    """Drop obviously broken proxy settings so AKShare can connect directly."""
    removed: List[str] = []
    for key in PROXY_ENV_VARS:
        value = os.environ.get(key)
        if not value:
            continue
        if force_disable or _looks_like_dead_local_proxy(value):
            removed.append(f"{key}={value}")
            os.environ.pop(key, None)
    return removed

try:
    import akshare as ak
except ImportError as exc:
    print("缺少依赖 akshare。请先运行：pip install -U akshare pandas numpy requests tqdm", file=sys.stderr)
    raise exc

try:
    from akshare.datasets import get_ths_js
except Exception:  # pragma: no cover
    get_ths_js = None

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover
    tqdm = lambda x, **kwargs: x


# =========================
# 1. 需要跟踪的板块清单
# =========================
# aliases 用于匹配 AKShare/东方财富中的概念名称。不同数据源命名可能略有差异，
# 所以每个板块给多个关键词，脚本会自动在“概念板块 + 行业板块”中模糊匹配。
TARGET_BOARDS: Dict[str, List[str]] = {
    "AI算力": ["算力", "算力租赁", "东数西算", "人工智能", "AI算力"],
    "光模块/光通信": ["光模块", "光通信", "光器件", "通信设备"],
    "CPO/硅光": ["CPO", "共封装光学", "硅光", "硅光子"],
    "PCB/CCL/电子布": ["PCB", "印制电路板", "覆铜板", "CCL", "电子布"],
    "AI服务器": ["AI服务器", "服务器", "云计算", "数据中心"],
    "液冷/数据中心温控": ["液冷", "液冷服务器", "数据中心", "温控", "IDC"],
    "算力租赁/IDC": ["算力租赁", "IDC", "东数西算", "云计算"],
    "半导体设备": ["半导体设备", "芯片设备", "光刻机", "刻蚀机"],
    "半导体材料": ["半导体材料", "电子化学品", "光刻胶", "电子特气", "靶材", "CMP"],
    "存储芯片": ["存储芯片", "存储器", "DRAM", "HBM", "NAND"],
    "长鑫/长江存储产业链": ["长鑫", "长鑫存储", "长江存储", "存储芯片", "半导体"],
    "先进封装/Chiplet": ["先进封装", "Chiplet", "封装", "HBM"],
    "封测/测试设备": ["封测", "芯片封测", "测试设备", "半导体测试"],
    "AI芯片/GPU/ASIC": ["AI芯片", "GPU", "ASIC", "国产芯片", "芯片设计"],
    "人形机器人": ["人形机器人", "机器人", "机器视觉"],
    "减速器/丝杠/电机/传感器": ["减速器", "丝杠", "电机", "传感器", "伺服"],
    "PEEK材料": ["PEEK", "peek材料", "工程塑料"],
    "智能驾驶/车路云": ["智能驾驶", "车路云", "无人驾驶", "V2X", "汽车电子"],
    "低空经济/eVTOL": ["低空经济", "eVTOL", "飞行汽车", "无人机"],
    "卫星互联网/商业航天": ["商业航天", "卫星互联网", "北斗导航", "军工电子"],
    "AI应用/大模型/Agent": ["AI应用", "大模型", "ChatGPT", "AIGC", "人工智能", "多模态AI"],
    "信创/国产软件": ["信创", "国产软件", "操作系统", "数据库", "软件开发"],
    "数据要素": ["数据要素", "数据确权", "数据中心", "政务数据"],
    "网络安全": ["网络安全", "数据安全", "信息安全", "密码安全"],
    "化工": ["化工", "基础化工", "化学原料", "化学制品", "化工原料", "化工行业"],
    "证券": ["证券", "券商", "证券板块", "多元金融", "互联网金融", "证券行业"],
    "食品饮料/白酒": ["食品饮料", "白酒", "啤酒", "乳业", "调味品", "饮料乳品", "休闲食品", "农产品加工"],
    "医美美妆/美容护理": ["美容护理", "医美", "医疗美容", "化妆品", "美妆", "个人护理", "护肤品"],
    "商贸零售/奢侈品/旅游酒店": ["商贸零售", "商业百货", "零售", "奢侈品", "珠宝首饰", "纺织服饰", "旅游酒店", "酒店餐饮", "免税店"],
    "AI手机/AI PC/消费电子": ["AI手机", "AI PC", "消费电子", "苹果概念", "智能穿戴"],
    "MR/AR/VR": ["MR", "AR", "VR", "虚拟现实", "增强现实", "混合现实"],
    "固态电池/储能/新能源科技": ["固态电池", "储能", "钠离子电池", "锂电池", "新能源"],
}


@dataclass
class BoardMatch:
    target: str
    matched_name: str
    board_type: str  # concept / industry
    score: float
    reason: str


DEFAULT_BOARD_CONFIG_PATH = board_config.DEFAULT_BOARD_CONFIG_PATH
TARGET_BOARDS = board_config.DEFAULT_TARGET_BOARDS.copy()


# =========================
# 2. 通用工具函数
# =========================
def today_str() -> str:
    return dt.datetime.now().strftime("%Y%m%d")


def display_date() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d")


def safe_float(x) -> float:
    if x is None:
        return np.nan
    if isinstance(x, (int, float, np.number)):
        return float(x)
    s = str(x).strip()
    if s in {"", "-", "--", "nan", "None"}:
        return np.nan
    # 处理百分号、逗号、中文单位
    s = s.replace(",", "").replace("%", "")
    mult = 1.0
    if s.endswith("万"):
        mult = 1e4
        s = s[:-1]
    elif s.endswith("亿"):
        mult = 1e8
        s = s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return np.nan


def normalize_name(s: str) -> str:
    s = str(s).lower()
    s = re.sub(r"[\s\-/（）()·_]+", "", s)
    return s


def pct_change(first: float, last: float) -> float:
    if first is None or last is None:
        return np.nan
    if not np.isfinite(first) or not np.isfinite(last) or first == 0:
        return np.nan
    return (last / first - 1.0) * 100.0


def fmt_pct(x: float) -> str:
    if not np.isfinite(x):
        return "NA"
    return f"{x:+.2f}%"


def fmt_money(x: float) -> str:
    if not np.isfinite(x):
        return "NA"
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1e8:
        return f"{sign}{x/1e8:.2f}亿"
    if x >= 1e4:
        return f"{sign}{x/1e4:.2f}万"
    return f"{sign}{x:.0f}"


def retry(func, *args, retries: int = 3, sleep: float = 1.2, **kwargs):
    last_exc = None
    for i in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover
            last_exc = exc
            if i < retries - 1:
                time.sleep(sleep * (i + 1))
    raise last_exc


def call_with_supported_kwargs(func, /, *args, **kwargs):
    """Call a function with only the kwargs it actually supports."""
    sig = inspect.signature(func)
    accepted = {}
    for key, value in kwargs.items():
        if key in sig.parameters:
            accepted[key] = value
    return func(*args, **accepted)


def make_request(url: str, *, params=None, headers=None, timeout: float = 20, verify: bool = True):
    return requests.get(url, params=params, headers=headers, timeout=timeout, verify=verify)


def get_ths_hexin_v() -> str:
    if py_mini_racer is None or get_ths_js is None:
        raise RuntimeError("同花顺数据源需要 py_mini_racer 和 akshare.datasets.get_ths_js")
    js_path = Path(get_ths_js("ths.js"))
    js_code = py_mini_racer.MiniRacer()
    js_code.eval(js_path.read_text(encoding="utf-8"))
    return js_code.call("v")


def get_ths_fund_flow_headers(kind: str) -> Dict[str, str]:
    if kind not in {"concept", "industry"}:
        raise ValueError(f"unsupported THS flow kind: {kind}")
    route = "gnzjl" if kind == "concept" else "hyzjl"
    return {
        "Accept": "text/html, */*; q=0.01",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "hexin-v": get_ths_hexin_v(),
        "Host": "data.10jqka.com.cn",
        "Pragma": "no-cache",
        "Referer": f"http://data.10jqka.com.cn/funds/{route}/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
    }


def fetch_board_universe_ak() -> pd.DataFrame:
    frames = []

    concept = retry(ak.stock_board_concept_name_em)
    concept = concept.copy()
    concept["board_type"] = "concept"
    if "板块名称" not in concept.columns:
        for c in concept.columns:
            if "名称" in str(c):
                concept = concept.rename(columns={c: "板块名称"})
                break
    frames.append(concept)

    industry = retry(ak.stock_board_industry_name_em)
    industry = industry.copy()
    industry["board_type"] = "industry"
    if "板块名称" not in industry.columns:
        for c in industry.columns:
            if "名称" in str(c):
                industry = industry.rename(columns={c: "板块名称"})
                break
    frames.append(industry)

    uni = pd.concat(frames, ignore_index=True, sort=False)
    if "板块名称" not in uni.columns:
        raise RuntimeError(f"板块名称列不存在，当前列：{list(uni.columns)}")
    uni = uni.dropna(subset=["板块名称"]).drop_duplicates(subset=["板块名称", "board_type"])
    uni["norm"] = uni["板块名称"].map(normalize_name)
    return uni


def fetch_board_universe_ths() -> pd.DataFrame:
    concept = retry(ak.stock_board_concept_name_ths).copy()
    concept = concept.rename(columns={"name": "板块名称", "code": "板块代码"})
    concept["board_type"] = "concept"

    industry = retry(ak.stock_board_industry_name_ths).copy()
    industry = industry.rename(columns={"name": "板块名称", "code": "板块代码"})
    industry["board_type"] = "industry"

    uni = pd.concat([concept, industry], ignore_index=True, sort=False)
    uni = uni.dropna(subset=["板块名称"]).drop_duplicates(subset=["板块名称", "board_type"])
    uni["norm"] = uni["板块名称"].map(normalize_name)
    return uni


def fetch_fund_flow_ak() -> pd.DataFrame:
    frames = []
    for sector_type in ["概念资金流", "行业资金流"]:
        for indicator in ["今日", "5日", "10日"]:
            df = retry(ak.stock_sector_fund_flow_rank, indicator=indicator, sector_type=sector_type)
            df = df.copy()
            df["sector_type"] = sector_type
            df["period"] = indicator
            if "板块名称" not in df.columns:
                for c in df.columns:
                    if "名称" in str(c):
                        df = df.rename(columns={c: "板块名称"})
                        break
            frames.append(df)
    flow = pd.concat(frames, ignore_index=True, sort=False)
    if "板块名称" in flow.columns:
        flow["norm"] = flow["板块名称"].map(normalize_name)
    return flow


def fetch_fund_flow_ths_one(kind: str, period: str) -> pd.DataFrame:
    route = "gnzjl" if kind == "concept" else "hyzjl"
    board_part = "" if period == "今日" else f"board/{period[:-1]}/"
    url = f"http://data.10jqka.com.cn/funds/{route}/{board_part}field/tradezdf/order/desc/page/1/ajax/1/free/1/"
    response = make_request(url, headers=get_ths_fund_flow_headers(kind), timeout=20)
    try:
        tables = pd.read_html(StringIO(response.text))
    except Exception as exc:
        preview = (response.text or "").strip().replace("\n", " ")[:160]
        raise RuntimeError(f"同花顺 {kind} {period} 资金流页面无可解析表格: {url} | preview={preview!r}") from exc
    if not tables:
        raise RuntimeError(f"同花顺 {kind} {period} 资金流返回空表")
    df = tables[0].copy()
    rename_map = {"行业": "板块名称", "涨跌幅": "板块涨跌幅", "阶段涨跌幅": "板块涨跌幅", "净额(亿)": "主力净流入-净额"}
    df = df.rename(columns=rename_map)
    if "板块名称" not in df.columns or "主力净流入-净额" not in df.columns:
        raise RuntimeError(f"同花顺 {kind} {period} 资金流字段异常: {list(df.columns)}")
    if "板块涨跌幅" in df.columns:
        df["板块涨跌幅"] = df["板块涨跌幅"].map(safe_float)
    df["主力净流入-净额"] = df["主力净流入-净额"].map(safe_float) * 1e8
    df["sector_type"] = "概念资金流" if kind == "concept" else "行业资金流"
    df["period"] = period
    df["norm"] = df["板块名称"].map(normalize_name)
    return df


def fetch_fund_flow_ths() -> pd.DataFrame:
    frames = []
    errors = []
    for kind in ["concept", "industry"]:
        for period in ["今日", "5日", "10日"]:
            try:
                frames.append(fetch_fund_flow_ths_one(kind, period))
            except Exception as exc:
                errors.append(f"{kind}/{period}: {exc}")
                print(f"[WARN] 同花顺资金流抓取失败 {kind}/{period}: {exc}", file=sys.stderr)
    if not frames:
        raise RuntimeError("同花顺资金流全部抓取失败。 " + " | ".join(errors))
    return pd.concat(frames, ignore_index=True, sort=False)


def get_history_ak(board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
    if board_type == "concept":
        df = retry(
            ak.stock_board_concept_hist_em,
            symbol=board_name,
            start_date=start_date,
            end_date=end_date,
            period="日k",
            adjust="",
        )
    else:
        df = retry(
            ak.stock_board_industry_hist_em,
            symbol=board_name,
            start_date=start_date,
            end_date=end_date,
            period="日k",
            adjust="",
        )
    df = df.copy()
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期")
    for col in ["收盘", "涨跌幅", "成交额", "换手率"]:
        if col in df.columns:
            df[col] = df[col].map(safe_float)
    return df


def get_history_ths(board_name: str, board_type: str, start_date: str, end_date: str) -> pd.DataFrame:
    if board_type == "concept":
        fn = ak.stock_board_concept_index_ths
    else:
        fn = ak.stock_board_industry_index_ths
    df = retry(fn, symbol=board_name, start_date=start_date, end_date=end_date)
    df = df.copy()
    rename_map = {
        "日期": "日期",
        "开盘价": "开盘",
        "最高价": "最高",
        "最低价": "最低",
        "收盘价": "收盘",
        "成交量": "成交量",
        "成交额": "成交额",
    }
    df = df.rename(columns=rename_map)
    if "日期" in df.columns:
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.sort_values("日期")
    for col in ["收盘", "成交额"]:
        if col in df.columns:
            df[col] = df[col].map(safe_float)
    if "收盘" in df.columns and "涨跌幅" not in df.columns:
        df["涨跌幅"] = df["收盘"].pct_change() * 100
    return df


# =========================
# 3. 数据抓取
# =========================
def fetch_board_universe(provider: str = "auto") -> pd.DataFrame:
    """获取概念板块和行业板块名称。"""
    if provider == "akshare":
        return fetch_board_universe_ak()
    if provider == "ths":
        return fetch_board_universe_ths()
    if provider != "auto":
        raise ValueError(f"unsupported provider: {provider}")

    errors = []
    for name, fn in [("akshare", fetch_board_universe_ak), ("ths", fetch_board_universe_ths)]:
        try:
            uni = fn()
            print(f"[INFO] 板块名称数据源: {name}")
            return uni
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print(f"[WARN] {name} 板块名称获取失败：{exc}", file=sys.stderr)
    raise RuntimeError("无法获取任何板块名称，请检查网络或数据源。 " + " | ".join(errors))


def fetch_fund_flow(provider: str = "auto") -> pd.DataFrame:
    """获取今日、5日、10日行业/概念资金流。"""
    if provider == "akshare":
        return fetch_fund_flow_ak()
    if provider == "ths":
        return fetch_fund_flow_ths()
    if provider != "auto":
        raise ValueError(f"unsupported provider: {provider}")

    errors = []
    for name, fn in [("akshare", fetch_fund_flow_ak), ("ths", fetch_fund_flow_ths)]:
        try:
            flow = fn()
            print(f"[INFO] 资金流数据源: {name}")
            return flow
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            print(f"[WARN] {name} 资金流获取失败：{exc}", file=sys.stderr)
    print("[WARN] 所有资金流数据源均失败，将继续生成不含资金流的结果。 " + " | ".join(errors), file=sys.stderr)
    return pd.DataFrame()


def get_history(board_name: str, board_type: str, start_date: str, end_date: str, provider: str = "auto") -> pd.DataFrame:
    """获取单个板块历史行情。"""
    if provider == "akshare":
        return get_history_ak(board_name, board_type, start_date, end_date)
    if provider == "ths":
        return get_history_ths(board_name, board_type, start_date, end_date)
    if provider != "auto":
        raise ValueError(f"unsupported provider: {provider}")

    last_exc = None
    for name, fn in [("akshare", get_history_ak), ("ths", get_history_ths)]:
        try:
            return fn(board_name, board_type, start_date, end_date)
        except Exception as exc:
            last_exc = exc
            print(f"[WARN] {name} 历史行情失败：{board_name}: {exc}", file=sys.stderr)
    raise last_exc


# =========================
# 4. 板块匹配与指标计算
# =========================
def match_one_target(target: str, aliases: List[str], universe: pd.DataFrame) -> Optional[BoardMatch]:
    names = universe[["板块名称", "board_type", "norm"]].drop_duplicates().to_dict("records")
    best: Optional[BoardMatch] = None

    # 1) 精确匹配优先
    for alias in aliases:
        na = normalize_name(alias)
        exact = universe[universe["norm"] == na]
        if not exact.empty:
            row = exact.iloc[0]
            return BoardMatch(target, row["板块名称"], row["board_type"], 1.0, f"exact:{alias}")

    # 2) 包含匹配
    for alias in aliases:
        na = normalize_name(alias)
        for row in names:
            nn = row["norm"]
            if not na or not nn:
                continue
            score = 0.0
            if na in nn:
                score = 0.92
            elif nn in na:
                score = 0.86
            if score > 0 and (best is None or score > best.score):
                best = BoardMatch(target, row["板块名称"], row["board_type"], score, f"contains:{alias}")

    # 3) 模糊匹配兜底
    for alias in aliases:
        na = normalize_name(alias)
        candidates = [(r["norm"], r) for r in names]
        close = difflib.get_close_matches(na, [c[0] for c in candidates], n=1, cutoff=0.55)
        if close:
            nn = close[0]
            row = next(r for n, r in candidates if n == nn)
            score = difflib.SequenceMatcher(None, na, nn).ratio()
            if best is None or score > best.score:
                best = BoardMatch(target, row["板块名称"], row["board_type"], score, f"fuzzy:{alias}")

    return best


def build_matches(universe: pd.DataFrame, target_boards: Dict[str, List[str]]) -> List[BoardMatch]:
    matches = []
    for target, aliases in target_boards.items():
        m = match_one_target(target, aliases, universe)
        if m is not None:
            matches.append(m)
        else:
            matches.append(BoardMatch(target, "", "", 0.0, "unmatched"))
    return matches


def find_flow_row(flow: pd.DataFrame, board_name: str, period: str) -> Optional[pd.Series]:
    if flow.empty or not board_name:
        return None
    nn = normalize_name(board_name)
    part = flow[(flow.get("period") == period) & (flow.get("norm") == nn)]
    if part.empty:
        # 资金流接口里的命名可能略不同，做一次 contains 匹配
        part = flow[(flow.get("period") == period) & (flow["norm"].astype(str).str.contains(nn, regex=False, na=False))]
    if part.empty:
        return None
    return part.iloc[0]


def flow_value(row: Optional[pd.Series], key_contains: str) -> float:
    if row is None:
        return np.nan
    # 常见列：主力净流入-净额、主力净流入-净占比
    for c in row.index:
        if key_contains in str(c):
            return safe_float(row[c])
    return np.nan


def label_board(pct1: float, pct5: float, pct20: float, flow_today: float, flow5: float, vol_ratio: float) -> str:
    """短线标签。"""
    p1 = pct1 if np.isfinite(pct1) else 0
    p5 = pct5 if np.isfinite(pct5) else 0
    p20 = pct20 if np.isfinite(pct20) else 0
    ft = flow_today if np.isfinite(flow_today) else 0
    f5 = flow5 if np.isfinite(flow5) else 0
    vr = vol_ratio if np.isfinite(vol_ratio) else 1

    if p20 >= 20 and ft < 0:
        return "高位分歧/谨慎追高"
    if p20 >= 20 and ft >= 0:
        return "高位强趋势"
    if p5 >= 8 and ft > 0:
        return "短线加速"
    if p20 <= 10 and p5 >= 2 and ft > 0 and vr >= 1.1:
        return "低位启动"
    if p20 <= 6 and f5 > 0:
        return "滞涨吸金"
    if p20 <= 5 and p1 > 0:
        return "低位异动"
    if ft < 0 and f5 < 0:
        return "资金流出/弱势"
    if p20 < 0:
        return "低位观察"
    return "中性轮动"


def score_board(pct1: float, pct5: float, pct20: float, flow_ratio: float, vol_ratio: float) -> float:
    """粗略景气度评分：越高代表短线越强。"""
    vals = []
    vals.append(np.nan_to_num(pct1, nan=0.0) * 0.20)
    vals.append(np.nan_to_num(pct5, nan=0.0) * 0.35)
    vals.append(np.nan_to_num(pct20, nan=0.0) * 0.20)
    vals.append(np.nan_to_num(flow_ratio, nan=0.0) * 0.20)
    vals.append((np.nan_to_num(vol_ratio, nan=1.0) - 1.0) * 5.0)
    return float(sum(vals))


def analyze_boards(matches: List[BoardMatch], flow: pd.DataFrame, lookback: int, sleep: float = 0.15, provider: str = "auto") -> pd.DataFrame:
    end = dt.datetime.now().strftime("%Y%m%d")
    start = (dt.datetime.now() - dt.timedelta(days=max(80, lookback * 4))).strftime("%Y%m%d")

    rows = []
    for m in tqdm(matches, desc="分析板块"):
        row = {
            "目标板块": m.target,
            "匹配板块": m.matched_name,
            "类型": m.board_type,
            "匹配分数": m.score,
            "匹配方式": m.reason,
        }
        if not m.matched_name:
            row.update({
                "1日涨跌幅%": np.nan,
                "5日涨跌幅%": np.nan,
                "20日涨跌幅%": np.nan,
                "成交额放量倍数": np.nan,
                "主力净流入_今日": np.nan,
                "主力净占比_今日%": np.nan,
                "主力净流入_5日": np.nan,
                "主力净流入_10日": np.nan,
                "景气度分": np.nan,
                "短线标签": "未匹配",
            })
            rows.append(row)
            continue

        try:
            hist = get_history(m.matched_name, m.board_type, start, end, provider=provider)
            if hist.empty or "收盘" not in hist.columns:
                raise RuntimeError("历史行情为空或缺少收盘列")
            h = hist.tail(max(lookback + 1, 21)).copy()
            close = h["收盘"].astype(float).values
            pct1 = safe_float(h.iloc[-1].get("涨跌幅", np.nan)) if "涨跌幅" in h.columns else pct_change(close[-2], close[-1])
            pct5 = pct_change(close[-6], close[-1]) if len(close) >= 6 else pct_change(close[0], close[-1])
            pct20 = pct_change(close[-21], close[-1]) if len(close) >= 21 else pct_change(close[0], close[-1])
            if "成交额" in h.columns and h["成交额"].notna().sum() >= 5:
                last_amt = float(h["成交额"].iloc[-1])
                med_amt = float(h["成交额"].iloc[:-1].tail(20).median())
                vol_ratio = last_amt / med_amt if med_amt > 0 else np.nan
            else:
                vol_ratio = np.nan
        except Exception as exc:
            print(f"[WARN] 历史行情失败：{m.target} -> {m.matched_name}: {exc}", file=sys.stderr)
            pct1 = pct5 = pct20 = vol_ratio = np.nan

        f_today = find_flow_row(flow, m.matched_name, "今日")
        f_5 = find_flow_row(flow, m.matched_name, "5日")
        f_10 = find_flow_row(flow, m.matched_name, "10日")
        main_today = flow_value(f_today, "主力净流入-净额")
        main_ratio_today = flow_value(f_today, "主力净流入-净占比")
        main_5 = flow_value(f_5, "主力净流入-净额")
        main_10 = flow_value(f_10, "主力净流入-净额")

        label = label_board(pct1, pct5, pct20, main_today, main_5, vol_ratio)
        score = score_board(pct1, pct5, pct20, main_ratio_today, vol_ratio)

        row.update({
            "1日涨跌幅%": pct1,
            "5日涨跌幅%": pct5,
            "20日涨跌幅%": pct20,
            "成交额放量倍数": vol_ratio,
            "主力净流入_今日": main_today,
            "主力净占比_今日%": main_ratio_today,
            "主力净流入_5日": main_5,
            "主力净流入_10日": main_10,
            "景气度分": score,
            "短线标签": label,
        })
        rows.append(row)
        time.sleep(sleep)

    df = pd.DataFrame(rows)
    if "景气度分" in df.columns:
        df = df.sort_values(["景气度分", "20日涨跌幅%"], ascending=[False, False], na_position="last")
    return df


# =========================
# 5. 报告生成
# =========================
def df_to_md_table(df: pd.DataFrame, cols: List[str], n: int = 10) -> str:
    if df.empty:
        return "无数据\n"
    tmp = df.loc[:, [c for c in cols if c in df.columns]].head(n).copy()
    for c in tmp.columns:
        if "涨跌幅" in c or "占比" in c:
            tmp[c] = tmp[c].map(lambda x: fmt_pct(x) if isinstance(x, (int, float, np.number)) and np.isfinite(x) else "NA")
        elif "净流入" in c:
            tmp[c] = tmp[c].map(lambda x: fmt_money(x) if isinstance(x, (int, float, np.number)) and np.isfinite(x) else "NA")
        elif "放量" in c or "景气度" in c:
            tmp[c] = tmp[c].map(lambda x: f"{x:.2f}" if isinstance(x, (int, float, np.number)) and np.isfinite(x) else "NA")
    return tmp.to_markdown(index=False)


def make_markdown_report(df: pd.DataFrame, report_date: str, lookback: int, topn: int) -> str:
    cols = [
        "目标板块", "匹配板块", "1日涨跌幅%", "5日涨跌幅%", "20日涨跌幅%",
        "成交额放量倍数", "主力净流入_今日", "主力净占比_今日%", "景气度分", "短线标签"
    ]

    hot = df.sort_values("景气度分", ascending=False, na_position="last")
    inflow = df.sort_values("主力净流入_今日", ascending=False, na_position="last")
    outflow = df.sort_values("主力净流入_今日", ascending=True, na_position="last")

    # 近20日涨幅不高，但今天/5日资金或走势开始转强
    low_candidates = df[
        (df["20日涨跌幅%"].fillna(999) <= 8)
        & (
            (df["主力净流入_今日"].fillna(0) > 0)
            | (df["5日涨跌幅%"].fillna(0) > 1.5)
            | (df["短线标签"].isin(["低位启动", "滞涨吸金", "低位异动", "低位观察"]))
        )
    ].sort_values(["主力净流入_今日", "5日涨跌幅%"], ascending=[False, False], na_position="last")

    high_risk = df[
        (df["20日涨跌幅%"].fillna(0) >= 15)
        | (df["短线标签"].isin(["高位分歧/谨慎追高", "高位强趋势", "短线加速"]))
    ].sort_values("20日涨跌幅%", ascending=False, na_position="last")

    weak = df[df["短线标签"].isin(["资金流出/弱势"])]
    weak = weak.sort_values("主力净流入_今日", ascending=True, na_position="last")

    md = []
    md.append(f"# A股科技/成长板块景气度与资金流日报\n")
    md.append(f"**日期：{report_date}**  \n")
    md.append(f"**统计口径：近 {lookback} 个交易日涨跌幅 + 东方财富板块资金流 今日/5日/10日。**\n")
    md.append("> 说明：本报告为量化复盘工具，不构成投资建议。板块名称来自 AKShare/东方财富，个别概念可能因命名差异被模糊匹配，请结合“匹配板块”和“匹配分数”检查。\n")

    md.append("## 1. 今日景气度最高\n")
    md.append(df_to_md_table(hot, cols, topn))

    md.append("\n## 2. 今日主力净流入靠前\n")
    md.append(df_to_md_table(inflow, cols, topn))

    md.append("\n## 3. 今日主力净流出靠前\n")
    md.append(df_to_md_table(outflow, cols, topn))

    md.append("\n## 4. 低位/滞涨但有启动迹象\n")
    if low_candidates.empty:
        md.append("暂无明显候选。\n")
    else:
        md.append(df_to_md_table(low_candidates, cols, topn))

    md.append("\n## 5. 已明显拉升或拥挤度较高\n")
    if high_risk.empty:
        md.append("暂无明显高位板块。\n")
    else:
        md.append(df_to_md_table(high_risk, cols, topn))

    md.append("\n## 6. 资金流出/弱势板块\n")
    if weak.empty:
        md.append("暂无明显连续弱势板块。\n")
    else:
        md.append(df_to_md_table(weak, cols, topn))

    md.append("\n## 7. 使用建议\n")
    md.append(
        "- 短线优先看：`低位启动`、`滞涨吸金`、`低位异动`，但必须结合板块核心股和盘中承接。\n"
        "- 对 `高位强趋势` 可以用作风向标，不建议无脑追高。\n"
        "- 对 `高位分歧/谨慎追高`，优先等待分歧后重新转强。\n"
        "- 对 `资金流出/弱势`，除非有明确催化，否则不做左侧硬抄底。\n"
    )
    return "\n".join(md)


def save_outputs(df: pd.DataFrame, out_dir: Path, report_date: str, lookback: int, topn: int) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"sector_summary_{report_date}.csv"
    md_path = out_dir / f"sector_report_{report_date}.md"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    md = make_markdown_report(df, report_date, lookback, topn)
    md_path.write_text(md, encoding="utf-8")
    return csv_path, md_path


# =========================
# 6. 主程序
# =========================
def main():
    parser = argparse.ArgumentParser(description="A股板块景气度与资金流日报")
    parser.add_argument("--out", default="./sector_report", help="输出目录")
    parser.add_argument("--lookback", type=int, default=20, help="近 N 个交易日涨跌幅，默认 20")
    parser.add_argument("--topn", type=int, default=10, help="报告每个榜单展示数量")
    parser.add_argument("--sleep", type=float, default=0.15, help="抓取单个板块后的暂停秒数，防止过快请求")
    parser.add_argument("--provider", choices=["auto", "akshare", "ths"], default="auto", help="数据源：auto 自动回退，akshare 东方财富，ths 同花顺")
    parser.add_argument("--no-proxy", action="store_true", help="忽略当前 Shell 代理，直连抓取 AKShare 数据")
    args = parser.parse_args()

    removed_proxies = sanitize_proxy_env(force_disable=args.no_proxy)
    if removed_proxies:
        print("[INFO] 已清理代理环境变量: " + "; ".join(removed_proxies))

    if args.provider == "auto":
        try:
            universe = fetch_board_universe_ak()
            effective_provider = "akshare"
            print("[INFO] 数据源自动选择: akshare")
        except Exception as exc:
            print(f"[WARN] akshare 板块名称获取失败：{exc}", file=sys.stderr)
            universe = fetch_board_universe_ths()
            effective_provider = "ths"
            print("[INFO] 数据源自动选择: ths")
    else:
        effective_provider = args.provider
        universe = fetch_board_universe(provider=effective_provider)

    report_date = today_str()
    print(f"[INFO] 开始生成板块日报：{display_date()}")
    print("[INFO] 获取板块名称...")
    print(f"[INFO] 板块 universe: {len(universe)}")

    print("[INFO] 匹配目标板块...")
    matches = build_matches(universe)
    match_df = pd.DataFrame([m.__dict__ for m in matches])
    unmatched = match_df[match_df["score"] <= 0]
    if not unmatched.empty:
        print("[WARN] 未匹配板块：" + ", ".join(unmatched["target"].tolist()), file=sys.stderr)

    print("[INFO] 获取资金流...")
    flow = fetch_fund_flow(provider=effective_provider)
    print(f"[INFO] 资金流记录：{len(flow)}")

    print("[INFO] 分析板块...")
    summary = analyze_boards(matches, flow, lookback=args.lookback, sleep=args.sleep, provider=effective_provider)

    out_dir = Path(args.out)
    csv_path, md_path = save_outputs(summary, out_dir, report_date, args.lookback, args.topn)
    match_path = out_dir / f"board_match_{report_date}.csv"
    match_df.to_csv(match_path, index=False, encoding="utf-8-sig")

    print("\n[OK] 已生成：")
    print(f"- 明细 CSV: {csv_path}")
    print(f"- 日报 MD : {md_path}")
    print(f"- 匹配表  : {match_path}")
    print("\n[提示] 如果某些板块匹配不准，请在 TARGET_BOARDS 里调整 aliases。")


def run_from_config():
    parser = argparse.ArgumentParser(description="A股板块景气度与资金流日报")
    parser.add_argument("--out", default="./sector_report", help="输出目录")
    parser.add_argument("--config", default=str(DEFAULT_BOARD_CONFIG_PATH), help="目标板块配置文件路径")
    parser.add_argument("--lookback", type=int, default=20, help="近 N 个交易日涨跌幅统计窗口")
    parser.add_argument("--topn", type=int, default=10, help="报告每个榜单显示数量")
    parser.add_argument("--sleep", type=float, default=0.15, help="抓取单个板块后的暂停秒数")
    parser.add_argument("--provider", choices=["auto", "akshare", "ths"], default="auto", help="数据源：auto 自动回退，akshare 东方财富，ths 同花顺")
    parser.add_argument("--skip-config-refresh", action="store_true", help="跳过运行时自动更新板块配置文件")
    parser.add_argument("--no-proxy", action="store_true", help="忽略当前 Shell 代理，直连抓取数据")
    args = parser.parse_args()

    removed_proxies = sanitize_proxy_env(force_disable=args.no_proxy)
    if removed_proxies:
        print("[INFO] 已清理代理环境变量: " + "; ".join(removed_proxies))

    if args.provider == "auto":
        try:
            universe = fetch_board_universe_ak()
            effective_provider = "akshare"
            print("[INFO] 数据源自动选择: akshare")
        except Exception as exc:
            print(f"[WARN] akshare 板块名称获取失败: {exc}", file=sys.stderr)
            universe = fetch_board_universe_ths()
            effective_provider = "ths"
            print("[INFO] 数据源自动选择: ths")
    else:
        effective_provider = args.provider
        universe = fetch_board_universe(provider=effective_provider)

    config_path = Path(args.config)
    refreshed_payload = None
    if args.skip_config_refresh:
        print(f"[INFO] 跳过自动更新板块配置: {config_path}")
    else:
        existing_payload = board_config.load_board_config(
            config_path=config_path,
            fallback_targets=TARGET_BOARDS,
        )
        refreshed_payload = board_config.build_board_config(
            universe=universe,
            provider=effective_provider,
            existing_payload=existing_payload,
        )
        board_count = sum(len(items) for items in refreshed_payload.get("board_catalog", {}).values())
        try:
            board_config.save_board_config(refreshed_payload, config_path)
            print(f"[INFO] 已自动更新板块配置: {config_path} ({board_count} 个可抓取板块)")
        except PermissionError as exc:
            print(f"[WARN] 板块配置文件写入失败，将继续使用本次内存中的最新板块列表: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"[WARN] 板块配置文件更新失败，将继续使用本次内存中的最新板块列表: {exc}", file=sys.stderr)

    if refreshed_payload is not None:
        target_boards = board_config.target_boards_from_payload(refreshed_payload)
    else:
        target_boards = board_config.load_target_boards(
            config_path=config_path,
            fallback_targets=TARGET_BOARDS,
        )

    report_date = today_str()
    print(f"[INFO] 开始生成板块日报: {display_date()}")
    print("[INFO] 获取板块名称...")
    print(f"[INFO] 板块 universe: {len(universe)}")
    print(f"[INFO] 配置中启用目标板块: {len(target_boards)}")

    print("[INFO] 匹配目标板块...")
    matches = build_matches(universe, target_boards)
    match_df = pd.DataFrame([m.__dict__ for m in matches])
    unmatched = match_df[match_df["score"] <= 0]
    if not unmatched.empty:
        print("[WARN] 未匹配板块: " + ", ".join(unmatched["target"].tolist()), file=sys.stderr)

    print("[INFO] 获取资金流...")
    try:
        flow = fetch_fund_flow(provider=effective_provider)
        print(f"[INFO] 资金流记录: {len(flow)}")
    except Exception as exc:
        print(f"[WARN] 资金流抓取失败，将继续生成不含资金流的日报: {exc}", file=sys.stderr)
        flow = pd.DataFrame()

    print("[INFO] 分析板块...")
    summary = analyze_boards(matches, flow, lookback=args.lookback, sleep=args.sleep, provider=effective_provider)

    out_dir = Path(args.out)
    csv_path, md_path = save_outputs(summary, out_dir, report_date, args.lookback, args.topn)
    match_path = out_dir / f"board_match_{report_date}.csv"
    match_df.to_csv(match_path, index=False, encoding="utf-8-sig")

    print("\n[OK] 已生成：")
    print(f"- 明细 CSV: {csv_path}")
    print(f"- 日报 MD : {md_path}")
    print(f"- 匹配表  : {match_path}")
    print(f"\n[提示] 如需调整目标板块或 aliases，请修改配置文件: {config_path}")


main = run_from_config


if __name__ == "__main__":
    run_from_config()
