#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

import ak_board_config
import board_config
import sector_daily_report as sdr


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_scope(payload: Dict, fallback: str) -> str:
    return str(payload.get("meta", {}).get("board_type") or fallback)


def _filter_universe(universe: pd.DataFrame, scope: str) -> pd.DataFrame:
    return universe[universe.get("board_type", "") == scope].copy()


def _run_one_scope(
    universe: pd.DataFrame,
    flow: pd.DataFrame,
    config_path: Path,
    scope_label: str,
    lookback: int,
    sleep: float,
    provider: str,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    payload = _load_json(config_path)
    scope = _resolve_scope(payload, scope_label)
    target_boards = board_config.target_boards_from_payload(payload)
    scope_universe = _filter_universe(universe, scope)

    print(f"[INFO] {scope_label}目标板块数: {len(target_boards)}")
    print(f"[INFO] {scope_label}可抓取板块数: {len(scope_universe)}")

    matches = sdr.build_matches(scope_universe, target_boards)
    match_df = pd.DataFrame([m.__dict__ for m in matches])
    summary = sdr.analyze_boards(matches, flow, lookback=lookback, sleep=sleep, provider=provider)
    summary["分析视角"] = "行业板块" if scope == "industry" else "概念板块"
    return summary, match_df


def _write_scope_outputs(
    out_dir: Path,
    scope_key: str,
    summary: pd.DataFrame,
    matches: pd.DataFrame,
    report_date: str,
) -> Tuple[Path, Path]:
    summary_path = out_dir / f"{scope_key}_summary_{report_date}.csv"
    match_path = out_dir / f"{scope_key}_match_{report_date}.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    matches.to_csv(match_path, index=False, encoding="utf-8-sig")
    return summary_path, match_path


def _make_dual_markdown(
    industry_df: pd.DataFrame,
    concept_df: pd.DataFrame,
    combined_df: pd.DataFrame,
    report_date: str,
    lookback: int,
    topn: int,
) -> str:
    cols = [
        "分析视角",
        "目标板块",
        "匹配板块",
        "1日涨跌幅%",
        "5日涨跌幅%",
        "20日涨跌幅%",
        "成交额放量倍数",
        "主力净流入_今日",
        "主力净占比_今日%",
        "景气度分",
        "短线标签",
    ]
    md: list[str] = []
    md.append(f"# AkShare 行业板块 + 概念板块日报\n")
    md.append(f"**日期：{report_date}**  \n")
    md.append(f"**统计窗口：近 {lookback} 个交易日**  \n")
    md.append("> 说明：行业板块更偏稳定结构，概念板块更偏热点题材。下方按总榜、行业榜、概念榜分别排序。\n")

    combined_hot = combined_df.sort_values(["景气度分", "20日涨跌幅%"], ascending=[False, False], na_position="last")
    industry_hot = industry_df.sort_values(["景气度分", "20日涨跌幅%"], ascending=[False, False], na_position="last")
    concept_hot = concept_df.sort_values(["景气度分", "20日涨跌幅%"], ascending=[False, False], na_position="last")
    industry_inflow = industry_df.sort_values("主力净流入_今日", ascending=False, na_position="last")
    concept_inflow = concept_df.sort_values("主力净流入_今日", ascending=False, na_position="last")

    md.append("## 1. 总榜排序\n")
    md.append(sdr.df_to_md_table(combined_hot, cols, topn))
    md.append("\n## 2. 行业板块排序\n")
    md.append(sdr.df_to_md_table(industry_hot, cols, topn))
    md.append("\n## 3. 概念板块排序\n")
    md.append(sdr.df_to_md_table(concept_hot, cols, topn))
    md.append("\n## 4. 行业板块主力净流入排序\n")
    md.append(sdr.df_to_md_table(industry_inflow, cols, topn))
    md.append("\n## 5. 概念板块主力净流入排序\n")
    md.append(sdr.df_to_md_table(concept_inflow, cols, topn))
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="按 AkShare 行业板块 + 概念板块生成双视角日报")
    parser.add_argument("--out", default="./sector_report", help="输出目录")
    parser.add_argument(
        "--industry-config",
        default=str(ak_board_config.DEFAULT_INDUSTRY_CONFIG_PATH),
        help="行业板块配置文件",
    )
    parser.add_argument(
        "--concept-config",
        default=str(ak_board_config.DEFAULT_CONCEPT_CONFIG_PATH),
        help="概念板块配置文件",
    )
    parser.add_argument("--lookback", type=int, default=20, help="近 N 个交易日统计窗口")
    parser.add_argument("--topn", type=int, default=10, help="每个榜单展示数量")
    parser.add_argument("--sleep", type=float, default=0.15, help="单板块抓取暂停秒数")
    parser.add_argument("--provider", choices=["auto", "akshare", "ths"], default="akshare", help="数据源")
    parser.add_argument("--no-proxy", action="store_true", help="忽略当前 Shell 代理")
    args = parser.parse_args()

    removed = sdr.sanitize_proxy_env(force_disable=args.no_proxy)
    if removed:
        print("[INFO] 已清理代理环境变量: " + "; ".join(removed))

    if args.provider == "auto":
        effective_provider, universe = sdr.resolve_universe_provider("auto")
    else:
        effective_provider = args.provider
        universe = sdr.fetch_board_universe(provider=effective_provider)
    print(f"[INFO] 数据源: {effective_provider}")
    print(f"[INFO] 板块 universe 总数: {len(universe)}")

    try:
        flow = sdr.fetch_fund_flow(provider=effective_provider)
    except Exception as exc:
        print(f"[WARN] 资金流抓取失败，将继续生成无资金流版本日报: {exc}", file=sys.stderr)
        flow = pd.DataFrame()

    industry_summary, industry_match = _run_one_scope(
        universe=universe,
        flow=flow,
        config_path=Path(args.industry_config),
        scope_label="industry",
        lookback=args.lookback,
        sleep=args.sleep,
        provider=effective_provider,
    )
    concept_summary, concept_match = _run_one_scope(
        universe=universe,
        flow=flow,
        config_path=Path(args.concept_config),
        scope_label="concept",
        lookback=args.lookback,
        sleep=args.sleep,
        provider=effective_provider,
    )

    combined = pd.concat([industry_summary, concept_summary], ignore_index=True, sort=False)
    combined = combined.sort_values(["景气度分", "20日涨跌幅%"], ascending=[False, False], na_position="last")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_date = sdr.today_str()

    industry_summary_path, industry_match_path = _write_scope_outputs(
        out_dir, "industry", industry_summary, industry_match, report_date
    )
    concept_summary_path, concept_match_path = _write_scope_outputs(
        out_dir, "concept", concept_summary, concept_match, report_date
    )
    combined_path = out_dir / f"board_dual_summary_{report_date}.csv"
    combined.to_csv(combined_path, index=False, encoding="utf-8-sig")

    md_path = out_dir / f"board_dual_report_{report_date}.md"
    md_path.write_text(
        _make_dual_markdown(
            industry_df=industry_summary,
            concept_df=concept_summary,
            combined_df=combined,
            report_date=sdr.display_date(),
            lookback=args.lookback,
            topn=args.topn,
        ),
        encoding="utf-8",
    )

    print("\n[OK] 已生成:")
    print(f"- 行业汇总: {industry_summary_path}")
    print(f"- 行业匹配: {industry_match_path}")
    print(f"- 概念汇总: {concept_summary_path}")
    print(f"- 概念匹配: {concept_match_path}")
    print(f"- 双视角总表: {combined_path}")
    print(f"- 双视角日报: {md_path}")


if __name__ == "__main__":
    main()
