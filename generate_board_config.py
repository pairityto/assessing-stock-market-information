#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
from pathlib import Path

import board_config
import sector_daily_report as sdr


def resolve_provider(provider: str) -> tuple[str, object]:
    if provider == "auto":
        try:
            universe = sdr.fetch_board_universe_ak()
            return "akshare", universe
        except Exception as exc:
            print(f"[WARN] akshare 板块列表获取失败，将回退到同花顺: {exc}")
            universe = sdr.fetch_board_universe_ths()
            return "ths", universe
    return provider, sdr.fetch_board_universe(provider=provider)


def main():
    parser = argparse.ArgumentParser(description="抓取全量板块并生成可编辑的板块配置文件")
    parser.add_argument("--provider", choices=["auto", "akshare", "ths"], default="auto", help="板块数据源")
    parser.add_argument("--out", default=str(board_config.DEFAULT_BOARD_CONFIG_PATH), help="输出 JSON 配置路径")
    parser.add_argument("--no-proxy", action="store_true", help="忽略当前 Shell 代理")
    args = parser.parse_args()

    removed = sdr.sanitize_proxy_env(force_disable=args.no_proxy)
    if removed:
        print("[INFO] 已清理代理环境变量: " + "; ".join(removed))

    effective_provider, universe = resolve_provider(args.provider)
    out_path = Path(args.out)
    existing_payload = board_config.load_board_config(
        config_path=out_path,
        fallback_targets=board_config.DEFAULT_TARGET_BOARDS,
    )
    payload = board_config.build_board_config(
        universe=universe,
        provider=effective_provider,
        existing_payload=existing_payload,
    )
    board_config.save_board_config(payload, out_path)

    total_targets = len(board_config.load_target_boards(out_path))
    total_boards = sum(len(items) for items in payload["board_catalog"].values())
    print(f"[OK] 已生成配置文件: {out_path}")
    print(f"[INFO] target_groups 中启用目标板块: {total_targets}")
    print(f"[INFO] board_catalog 中收录可抓取板块: {total_boards}")
    print("[INFO] 你可以直接编辑 target_groups，sector_daily_report 会按这个文件读取目标板块。")


if __name__ == "__main__":
    main()
