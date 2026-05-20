#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从“目标板块”继续下钻，找出最相关的股票。

相关性的定义（综合评分）：
1. 板块归属相关性：股票属于与目标板块最贴近的真实板块，匹配分越高越相关
2. 交叉出现次数：同一只股票若同时出现在该目标板块的多个相关子板块中，视为更核心
3. 板块内排名：在同花顺板块成份页中位置越靠前，默认越核心/活跃

输出：
- CSV 明细：每个目标板块对应的相关股票、评分、原因、股票代码

“走势相关”额外参考：
1. 当日涨跌幅：更强的价格响应优先
2. 换手率、量比：更活跃的交易特征优先
3. 板块内排序：同花顺详情页默认靠前的股票通常更核心

示例：
    python sector_related_stocks.py
    python sector_related_stocks.py --target "AI算力"
    python sector_related_stocks.py --target "AI算力" "半导体设备" --topn 8 --out ./sector_report
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
from typing import Dict, List

import pandas as pd

import board_config
import sector_daily_report as sdr


def find_candidate_boards(target: str, aliases: List[str], universe: pd.DataFrame, max_candidates: int = 5) -> List[sdr.BoardMatch]:
    """Find several close board candidates instead of just one best match."""
    names = universe[["板块名称", "板块代码", "board_type", "norm"]].drop_duplicates().to_dict("records")
    candidates: Dict[tuple, sdr.BoardMatch] = {}

    def upsert(match: sdr.BoardMatch):
        key = (match.matched_name, match.board_type)
        prev = candidates.get(key)
        if prev is None or match.score > prev.score:
            candidates[key] = match

    for alias in aliases:
        na = sdr.normalize_name(alias)
        if not na:
            continue
        exact = universe[universe["norm"] == na]
        for _, row in exact.iterrows():
            upsert(sdr.BoardMatch(target, row["板块名称"], row["board_type"], 1.0, f"exact:{alias}"))
        for row in names:
            nn = row["norm"]
            if not nn:
                continue
            if na in nn:
                upsert(sdr.BoardMatch(target, row["板块名称"], row["board_type"], 0.92, f"contains:{alias}"))
            elif nn in na:
                upsert(sdr.BoardMatch(target, row["板块名称"], row["board_type"], 0.86, f"contains-rev:{alias}"))
        close = sdr.difflib.get_close_matches(na, [r["norm"] for r in names], n=3, cutoff=0.60)
        for nn in close:
            row = next(r for r in names if r["norm"] == nn)
            score = sdr.difflib.SequenceMatcher(None, na, nn).ratio()
            upsert(sdr.BoardMatch(target, row["板块名称"], row["board_type"], score, f"fuzzy:{alias}"))

    ranked = sorted(candidates.values(), key=lambda x: x.score, reverse=True)
    return ranked[:max_candidates]


def resolve_requested_targets(raw_targets: List[str] | None) -> Dict[str, List[str]]:
    """Allow exact target names plus simple fuzzy matching against configured targets."""
    if not raw_targets:
        return sdr.TARGET_BOARDS

    selected: Dict[str, List[str]] = {}
    all_names = list(sdr.TARGET_BOARDS.keys())
    for raw in raw_targets:
        parts = [item.strip() for item in str(raw).split(",") if item.strip()]
        for part in parts:
            if part in sdr.TARGET_BOARDS:
                selected[part] = sdr.TARGET_BOARDS[part]
                continue
            norm = sdr.normalize_name(part)
            exact = [name for name in all_names if sdr.normalize_name(name) == norm]
            if exact:
                selected[exact[0]] = sdr.TARGET_BOARDS[exact[0]]
                continue
            contains = [name for name in all_names if norm and (norm in sdr.normalize_name(name) or sdr.normalize_name(name) in norm)]
            if contains:
                selected[contains[0]] = sdr.TARGET_BOARDS[contains[0]]
                continue
            close = sdr.difflib.get_close_matches(part, all_names, n=1, cutoff=0.45)
            if close:
                selected[close[0]] = sdr.TARGET_BOARDS[close[0]]
                continue
            raise ValueError(f"未识别目标板块: {part}")
    return selected


def get_board_code(board_name: str, board_type: str, universe: pd.DataFrame) -> str:
    part = universe[(universe["板块名称"] == board_name) & (universe["board_type"] == board_type)]
    if part.empty or "板块代码" not in part.columns:
        raise RuntimeError(f"找不到板块代码: {board_name} / {board_type}")
    return str(part.iloc[0]["板块代码"])


def fetch_components_ths(board_name: str, board_type: str, board_code: str) -> pd.DataFrame:
    """Scrape all constituent stocks from THS board detail pages."""
    if board_type == "concept":
        base_url = f"https://q.10jqka.com.cn/gn/detail/code/{board_code}/"
    else:
        base_url = f"https://q.10jqka.com.cn/thshy/detail/code/{board_code}/"

    headers = {"User-Agent": "Mozilla/5.0"}
    cookie_v = None
    try:
        cookie_v = sdr.get_ths_hexin_v()
    except Exception:
        cookie_v = None
    if cookie_v:
        headers["Cookie"] = f"v={cookie_v}"

    first_resp = sdr.make_request(base_url, headers=headers, timeout=20)
    try:
        tables = pd.read_html(sdr.StringIO(first_resp.text))
    except ValueError as exc:
        raise RuntimeError(f"No tables found @ {base_url}") from exc
    if not tables:
        raise RuntimeError(f"No tables found @ {base_url}")
    first_df = tables[0].copy()
    if sdr.BeautifulSoup is None:
        total_pages = 1
    else:
        soup = sdr.BeautifulSoup(first_resp.text, "lxml")
        page_info = soup.find(attrs={"class": "page_info"})
        total_pages = int(page_info.get_text(strip=True).split("/")[-1]) if page_info else 1

    frames = [first_df]
    for page in range(2, total_pages + 1):
        page_url = base_url.rstrip("/") + f"/order/desc/page/{page}/"
        resp = sdr.make_request(page_url, headers=headers, timeout=20)
        try:
            page_tables = pd.read_html(sdr.StringIO(resp.text))
        except ValueError:
            continue
        if not page_tables:
            continue
        frames.append(page_tables[0].copy())

    df = pd.concat(frames, ignore_index=True)
    rename_map = {
        "序号": "板块内序号",
        "代码": "股票代码",
        "名称": "股票名称",
        "现价": "现价",
        "现价(元)": "现价",
        "涨跌幅(%)": "涨跌幅%",
        "涨跌幅": "涨跌幅%",
        "涨跌": "涨跌",
        "涨速(%)": "涨速%",
        "换手(%)": "换手%",
        "量比": "量比",
        "振幅(%)": "振幅%",
        "成交额": "成交额",
        "流通股": "流通股",
        "流通市值": "流通市值",
        "市盈率": "市盈率",
    }
    df = df.rename(columns=rename_map)
    keep_cols = [c for c in ["板块内序号", "股票代码", "股票名称", "现价", "涨跌幅%", "涨跌", "涨速%", "换手%", "量比", "振幅%", "成交额", "流通股", "流通市值", "市盈率"] if c in df.columns]
    df = df.loc[:, keep_cols].copy()
    df["股票代码"] = df["股票代码"].astype(str).str.zfill(6)
    df["板块名称"] = board_name
    df["板块类型"] = board_type
    if "板块内序号" in df.columns:
        df["板块内序号"] = pd.to_numeric(df["板块内序号"], errors="coerce")
    for col in ["现价", "涨跌幅%", "涨跌", "涨速%", "换手%", "量比", "振幅%"]:
        if col in df.columns:
            df[col] = df[col].map(sdr.safe_float)
    return df


def fetch_components_em(board_name: str, board_type: str) -> pd.DataFrame:
    if board_type == "concept":
        df = sdr.retry(sdr.ak.stock_board_concept_cons_em, symbol=board_name)
    else:
        df = sdr.retry(sdr.ak.stock_board_industry_cons_em, symbol=board_name)

    df = df.rename(
        columns={
            "序号": "板块内序号",
            "代码": "股票代码",
            "名称": "股票名称",
            "最新价": "现价",
            "涨跌幅": "涨跌幅%",
            "涨跌额": "涨跌",
            "成交额": "成交额",
            "换手率": "换手%",
            "振幅": "振幅%",
            "市盈率-动态": "市盈率",
        }
    ).copy()
    keep_cols = [c for c in ["板块内序号", "股票代码", "股票名称", "现价", "涨跌幅%", "涨跌", "换手%", "振幅%", "成交额", "市盈率"] if c in df.columns]
    df = df.loc[:, keep_cols].copy()
    df["股票代码"] = df["股票代码"].astype(str).str.zfill(6)
    df["板块名称"] = board_name
    df["板块类型"] = board_type
    if "板块内序号" in df.columns:
        df["板块内序号"] = pd.to_numeric(df["板块内序号"], errors="coerce")
    for col in ["现价", "涨跌幅%", "涨跌", "换手%", "振幅%", "成交额"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_components(board_name: str, board_type: str, board_code: str, component_provider: str = "auto") -> tuple[pd.DataFrame, str]:
    if component_provider == "em":
        return fetch_components_em(board_name, board_type), "em"
    if component_provider == "ths":
        return fetch_components_ths(board_name, board_type, board_code), "ths"
    if component_provider != "auto":
        raise ValueError(f"unsupported component provider: {component_provider}")

    errors = []
    for provider_name in ["em", "ths"]:
        try:
            if provider_name == "em":
                return fetch_components_em(board_name, board_type), provider_name
            return fetch_components_ths(board_name, board_type, board_code), provider_name
        except Exception as exc:
            errors.append(f"{provider_name}: {exc}")
    raise RuntimeError(" | ".join(errors))


def aggregate_related_stocks(
    target: str,
    matches: List[sdr.BoardMatch],
    universe: pd.DataFrame,
    component_provider: str = "auto",
) -> pd.DataFrame:
    rows = []
    for match in matches:
        try:
            board_code = get_board_code(match.matched_name, match.board_type, universe)
            comp, used_provider = fetch_components(match.matched_name, match.board_type, board_code, component_provider=component_provider)
        except Exception as exc:
            print(f"[WARN] 成份股抓取失败：{target} -> {match.matched_name}: {exc}")
            continue
        if comp.empty:
            continue
        comp["目标板块"] = target
        comp["匹配板块"] = match.matched_name
        comp["匹配类型"] = match.board_type
        comp["板块匹配分"] = match.score
        comp["匹配依据"] = match.reason
        comp["成份股来源"] = used_provider
        rows.append(comp)

    if not rows:
        return pd.DataFrame()
    raw = pd.concat(rows, ignore_index=True)

    agg_rows = []
    for stock_code, group in raw.groupby("股票代码", dropna=False):
        best = group.sort_values(["板块匹配分", "板块内序号"], ascending=[False, True], na_position="last").iloc[0]
        board_count = group["匹配板块"].nunique()
        best_rank = float(group["板块内序号"].min()) if "板块内序号" in group.columns else math.nan
        membership_score = 0.0
        for _, row in group.iterrows():
            rank = row.get("板块内序号", math.nan)
            rank_factor = 1.0 if not pd.notna(rank) else 1.0 / max(math.sqrt(float(rank)), 1.0)
            membership_score += float(row["板块匹配分"]) * 100 * rank_factor
        pct = sdr.safe_float(best.get("涨跌幅%", math.nan))
        turnover = sdr.safe_float(best.get("换手%", math.nan))
        volume_ratio = sdr.safe_float(best.get("量比", math.nan))
        trend_score = max(pct, 0) * 2.0 + max(turnover, 0) * 0.6 + max(volume_ratio - 1.0, 0) * 8.0
        final_score = membership_score + max(board_count - 1, 0) * 15 + trend_score
        agg_rows.append(
            {
                "目标板块": target,
                "股票代码": stock_code,
                "股票名称": best["股票名称"],
                "相关度分": round(final_score, 2),
                "走势强度分": round(trend_score, 2),
                "命中板块数": board_count,
                "最佳匹配板块": best["匹配板块"],
                "最佳匹配类型": best["匹配类型"],
                "最佳板块内排名": best_rank,
                "板块匹配分": round(float(best["板块匹配分"]), 4),
                "匹配依据": best["匹配依据"],
                "相关性说明": (
                    f"属于 {board_count} 个相关板块；最佳板块={best['匹配板块']}；"
                    f"最佳排名={int(best_rank) if pd.notna(best_rank) else 'NA'}；"
                    f"当日涨跌幅={pct if pd.notna(pct) else 'NA'}%"
                ),
                "现价": best.get("现价", math.nan),
                "涨跌幅%": best.get("涨跌幅%", math.nan),
                "换手%": best.get("换手%", math.nan),
                "量比": best.get("量比", math.nan),
                "成交额": best.get("成交额", None),
                "流通市值": best.get("流通市值", None),
            }
        )
    result = pd.DataFrame(agg_rows)
    result = result.sort_values(["相关度分", "走势强度分", "命中板块数", "最佳板块内排名"], ascending=[False, False, False, True], na_position="last")
    return result


def build_related_stock_report(topn: int = 10, max_board_candidates: int = 5, requested_targets: List[str] | None = None) -> pd.DataFrame:
    universe = sdr.fetch_board_universe_ths()
    all_rows = []
    target_map = resolve_requested_targets(requested_targets)
    for target, aliases in target_map.items():
        matches = find_candidate_boards(target, aliases, universe, max_candidates=max_board_candidates)
        if not matches:
            continue
        related = aggregate_related_stocks(target, matches, universe)
        if related.empty:
            continue
        all_rows.append(related.head(topn))
    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)


def save_outputs(df: pd.DataFrame, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    report_date = sdr.today_str()
    csv_path = out_dir / f"sector_related_stocks_{report_date}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return csv_path


def main():
    parser = argparse.ArgumentParser(description="查找目标板块中最相关的股票")
    parser.add_argument("--target", nargs="+", help="输入一个或多个目标板块名，支持空格分隔或逗号分隔")
    parser.add_argument("--topn", type=int, default=10, help="每个目标板块输出前 N 只股票")
    parser.add_argument("--max-board-candidates", type=int, default=5, help="每个目标板块最多展开多少个候选真实板块")
    parser.add_argument("--out", default="./sector_report", help="输出目录")
    parser.add_argument("--no-proxy", action="store_true", help="忽略当前 Shell 代理")
    args = parser.parse_args()

    removed = sdr.sanitize_proxy_env(force_disable=args.no_proxy)
    if removed:
        print("[INFO] 已清理代理环境变量: " + "; ".join(removed))

    print("[INFO] 构建目标板块相关股票列表...")
    df = build_related_stock_report(
        topn=args.topn,
        max_board_candidates=args.max_board_candidates,
        requested_targets=args.target,
    )
    if df.empty:
        raise RuntimeError("未获取到任何相关股票，请检查网络或数据源。")
    csv_path = save_outputs(df, Path(args.out))
    print(f"[OK] 已生成: {csv_path}")
    sample = df[["目标板块", "股票代码", "股票名称", "相关度分", "走势强度分", "涨跌幅%", "换手%", "量比", "相关性说明"]].head(20)
    with pd.option_context("display.max_rows", None, "display.max_columns", None, "display.width", 200):
        print(sample.to_string(index=False))


def resolve_requested_targets_from_config(raw_targets: List[str] | None, config_path: str | Path | None = None) -> Dict[str, List[str]]:
    target_boards = board_config.load_target_boards(
        config_path=config_path,
        fallback_targets=sdr.TARGET_BOARDS,
    )
    if not raw_targets:
        return target_boards

    selected: Dict[str, List[str]] = {}
    all_names = list(target_boards.keys())
    for raw in raw_targets:
        parts = [item.strip() for item in str(raw).split(",") if item.strip()]
        for part in parts:
            if part in target_boards:
                selected[part] = target_boards[part]
                continue
            norm = sdr.normalize_name(part)
            exact = [name for name in all_names if sdr.normalize_name(name) == norm]
            if exact:
                selected[exact[0]] = target_boards[exact[0]]
                continue
            contains = [name for name in all_names if norm and (norm in sdr.normalize_name(name) or sdr.normalize_name(name) in norm)]
            if contains:
                selected[contains[0]] = target_boards[contains[0]]
                continue
            close = sdr.difflib.get_close_matches(part, all_names, n=1, cutoff=0.45)
            if close:
                selected[close[0]] = target_boards[close[0]]
                continue
            raise ValueError(f"未识别目标板块: {part}")
    return selected


def build_related_stock_report_from_config(
    topn: int = 10,
    max_board_candidates: int = 5,
    requested_targets: List[str] | None = None,
    config_path: str | Path | None = None,
    component_provider: str = "auto",
) -> pd.DataFrame:
    universe = sdr.fetch_board_universe_ths()
    all_rows = []
    target_map = resolve_requested_targets_from_config(requested_targets, config_path=config_path)
    for target, aliases in target_map.items():
        matches = find_candidate_boards(target, aliases, universe, max_candidates=max_board_candidates)
        if not matches:
            continue
        related = aggregate_related_stocks(target, matches, universe, component_provider=component_provider)
        if related.empty:
            continue
        all_rows.append(related.head(topn))
    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)


def run_cli():
    parser = argparse.ArgumentParser(description="查找目标板块中最相关的股票")
    parser.add_argument("--target", nargs="+", help="输入一个或多个目标板块名，支持空格分隔或逗号分隔")
    parser.add_argument("--topn", type=int, default=10, help="每个目标板块输出前 N 只股票")
    parser.add_argument("--max-board-candidates", type=int, default=5, help="每个目标板块最多展开多少个候选真实板块")
    parser.add_argument("--out", default="./sector_report", help="输出目录")
    parser.add_argument("--config", default=str(board_config.DEFAULT_BOARD_CONFIG_PATH), help="目标板块配置文件路径")
    parser.add_argument("--component-provider", choices=["auto", "em", "ths"], default="auto", help="成份股来源：auto 先东财后同花顺")
    parser.add_argument("--no-proxy", action="store_true", help="忽略当前 Shell 代理")
    args = parser.parse_args()

    removed = sdr.sanitize_proxy_env(force_disable=args.no_proxy)
    if removed:
        print("[INFO] 已清理代理环境变量: " + "; ".join(removed))

    print("[INFO] 构建目标板块相关股票列表...")
    df = build_related_stock_report_from_config(
        topn=args.topn,
        max_board_candidates=args.max_board_candidates,
        requested_targets=args.target,
        config_path=args.config,
        component_provider=args.component_provider,
    )
    if df.empty:
        raise RuntimeError("未获取到任何相关股票，请检查网络、配置文件或数据源。")
    csv_path = save_outputs(df, Path(args.out))
    print(f"[OK] 已生成 {csv_path}")
    sample = df[["目标板块", "股票代码", "股票名称", "相关度分", "走势强度分", "涨跌幅%", "换手%", "量比", "相关性说明"]].head(20)
    with pd.option_context("display.max_rows", None, "display.max_columns", None, "display.width", 200):
        print(sample.to_string(index=False))


main = run_cli


if __name__ == "__main__":
    run_cli()
