#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
from pathlib import Path

import ak_board_config
import sector_daily_report as sdr


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 AkShare 行业板块 / 概念板块配置文件")
    parser.add_argument(
        "--industry-out",
        default=str(ak_board_config.DEFAULT_INDUSTRY_CONFIG_PATH),
        help="行业板块配置输出路径",
    )
    parser.add_argument(
        "--concept-out",
        default=str(ak_board_config.DEFAULT_CONCEPT_CONFIG_PATH),
        help="概念板块配置输出路径",
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "akshare", "ths"],
        default="akshare",
        help="板块 universe 抓取来源，默认 akshare",
    )
    parser.add_argument("--no-proxy", action="store_true", help="忽略当前 Shell 代理")
    args = parser.parse_args()

    removed = sdr.sanitize_proxy_env(force_disable=args.no_proxy)
    if removed:
        print("[INFO] 已清理代理环境变量: " + "; ".join(removed))

    industry_path = Path(args.industry_out)
    concept_path = Path(args.concept_out)

    industry_existing = ak_board_config.load_payload(industry_path)
    concept_existing = ak_board_config.load_payload(concept_path)

    try:
        if args.provider == "auto":
            effective_provider, universe = sdr.resolve_universe_provider("auto")
        else:
            effective_provider = args.provider
            universe = sdr.fetch_board_universe(provider=effective_provider)
        print(f"[INFO] 板块 universe 来源: {effective_provider}")
        print(f"[INFO] 板块 universe 总数: {len(universe)}")
    except Exception as exc:
        print(f"[WARN] 板块列表抓取失败，回退到本地模板配置: {exc}")
        ak_board_config.save_payload(industry_existing, industry_path)
        ak_board_config.save_payload(concept_existing, concept_path)
        print(f"[OK] 行业板块配置: {industry_path} (模板已保留)")
        print(f"[OK] 概念板块配置: {concept_path} (模板已保留)")
        return

    industry_payload = ak_board_config.payload_from_universe(
        universe=universe,
        scope="industry",
        existing_payload=industry_existing,
    )
    concept_payload = ak_board_config.payload_from_universe(
        universe=universe,
        scope="concept",
        existing_payload=concept_existing,
    )

    ak_board_config.save_payload(industry_payload, industry_path)
    ak_board_config.save_payload(concept_payload, concept_path)

    industry_count = len(industry_payload.get("target_groups", {}).get("industry", []))
    concept_count = len(concept_payload.get("target_groups", {}).get("concept", []))
    print(f"[OK] 行业板块配置: {industry_path} (已选 {industry_count} 个)")
    print(f"[OK] 概念板块配置: {concept_path} (已选 {concept_count} 个)")


if __name__ == "__main__":
    main()
