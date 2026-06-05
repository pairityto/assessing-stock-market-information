import argparse
from pathlib import Path

from board_report_core import (
    CONFIG_PATH,
    OUTPUT_DIR,
    analyze_selected_boards,
    load_config,
    sanitize_proxy_env,
    save_config,
    save_report_outputs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate daily board/concept report from saved config.")
    parser.add_argument("--config", default=str(CONFIG_PATH), help="Config JSON path")
    parser.add_argument("--out", default=str(OUTPUT_DIR), help="Output directory")
    parser.add_argument("--provider", choices=["akshare", "eastmoney", "ths"], default=None, help="Override provider in config")
    parser.add_argument("--lookback", type=int, default=None, help="Override lookback window")
    parser.add_argument("--topn", type=int, default=None, help="Override topn for HTML sections")
    parser.add_argument("--sleep", type=float, default=None, help="Override pause seconds between board requests")
    parser.add_argument("--no-proxy", action="store_true", help="Clear proxy environment before fetching")
    args = parser.parse_args()

    removed = sanitize_proxy_env(force_disable=args.no_proxy)
    config = load_config(Path(args.config))
    if args.provider:
        config["meta"]["provider"] = args.provider
    if args.lookback is not None:
        config["meta"]["lookback"] = args.lookback
    if args.topn is not None:
        config["meta"]["topn"] = args.topn
    if args.sleep is not None:
        config["meta"]["sleep"] = args.sleep

    save_config(config, Path(args.config))
    df = analyze_selected_boards(config)
    outputs = save_report_outputs(df, config, Path(args.out))

    if removed:
        print("[INFO] Cleared proxy env:", "; ".join(removed))
    print("[OK] Generated:")
    print(f"- CSV  : {outputs['csv']}")
    print(f"- HTML : {outputs['html']}")
    print(f"- CONF : {outputs['config']}")


if __name__ == "__main__":
    main()
