#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

import sector_daily_report as sdr

DEFAULT_INDUSTRY_CONFIG_PATH = Path("./board_targets_ak_industry.json")
DEFAULT_CONCEPT_CONFIG_PATH = Path("./board_targets_ak_concept.json")

DEFAULT_INDUSTRY_SELECTION: Dict[str, Any] = {
    "scope": "industry",
    "description": "AkShare 东方财富行业板块配置。可按 exact_names / include_keywords / exclude_keywords 选择今日分析板块。",
    "exact_names": [
        "半导体",
        "证券",
        "通信设备",
        "软件开发",
        "电池",
        "自动化设备",
    ],
    "include_keywords": [],
    "exclude_keywords": [],
}

DEFAULT_CONCEPT_SELECTION: Dict[str, Any] = {
    "scope": "concept",
    "description": "AkShare 东方财富概念板块配置。适合追踪 AI/算力/AIDC/CPO 等新主题。",
    "exact_names": [
        "算力概念",
        "东数西算",
        "数据中心",
        "液冷服务器",
        "CPO概念",
        "AIGC概念",
        "AI智能体",
        "AI芯片",
    ],
    "include_keywords": [
        "AI",
        "算力",
        "数据中心",
        "液冷",
        "光模块",
        "CPO",
    ],
    "exclude_keywords": [],
}


def _ensure_board_name_columns(universe: pd.DataFrame) -> pd.DataFrame:
    df = universe.copy()
    if "板块名称" not in df.columns:
        for col in df.columns:
            if "名称" in str(col):
                df = df.rename(columns={col: "板块名称"})
                break
    if "板块代码" not in df.columns:
        for col in df.columns:
            if "代码" in str(col):
                df = df.rename(columns={col: "板块代码"})
                break
    return df


def default_payload(scope: str) -> Dict[str, Any]:
    selection = copy.deepcopy(
        DEFAULT_INDUSTRY_SELECTION if scope == "industry" else DEFAULT_CONCEPT_SELECTION
    )
    return {
        "meta": {
            "schema_version": 1,
            "generated_at": None,
            "source_provider": "akshare",
            "board_type": scope,
            "description": selection["description"],
        },
        "analysis_selection": selection,
        "target_groups": {scope: []},
        "board_catalog": {scope: []},
    }


def iter_board_catalog(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for items in payload.get("board_catalog", {}).values():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                yield item


def select_board_names(board_names: List[str], selection: Dict[str, Any]) -> List[str]:
    exact_names = [str(x).strip() for x in selection.get("exact_names", []) if str(x).strip()]
    include_keywords = [str(x).strip() for x in selection.get("include_keywords", []) if str(x).strip()]
    exclude_keywords = [str(x).strip() for x in selection.get("exclude_keywords", []) if str(x).strip()]

    selected: List[str] = []
    for board_name in board_names:
        norm_name = sdr.normalize_name(board_name)
        matched_exact = any(sdr.normalize_name(item) == norm_name for item in exact_names)
        matched_keyword = any(
            sdr.normalize_name(keyword) and sdr.normalize_name(keyword) in norm_name
            for keyword in include_keywords
        )
        excluded = any(
            sdr.normalize_name(keyword) and sdr.normalize_name(keyword) in norm_name
            for keyword in exclude_keywords
        )
        if excluded:
            continue
        if matched_exact or matched_keyword:
            selected.append(board_name)

    if not exact_names and not include_keywords:
        selected = [name for name in board_names if not any(
            sdr.normalize_name(keyword) and sdr.normalize_name(keyword) in sdr.normalize_name(name)
            for keyword in exclude_keywords
        )]
    return selected


def payload_from_universe(
    universe: pd.DataFrame,
    scope: str,
    existing_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = copy.deepcopy(existing_payload) if existing_payload else default_payload(scope)
    payload.setdefault("analysis_selection", default_payload(scope)["analysis_selection"])
    payload.setdefault("meta", {})
    payload["meta"].update(
        {
            "schema_version": 1,
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_provider": "akshare",
            "board_type": scope,
        }
    )

    df = _ensure_board_name_columns(universe)
    df = df[df.get("board_type", "") == scope].copy()
    if "板块名称" not in df.columns:
        raise ValueError("universe missing 板块名称 column")
    if "板块代码" not in df.columns:
        df["板块代码"] = ""

    df = df.dropna(subset=["板块名称"]).drop_duplicates(subset=["板块名称"]).sort_values("板块名称")
    board_names = df["板块名称"].astype(str).tolist()
    selected_names = select_board_names(board_names, payload["analysis_selection"])

    payload["target_groups"] = {
        scope: [
            {"target": board_name, "aliases": [board_name], "enabled": True}
            for board_name in selected_names
        ]
    }
    payload["board_catalog"] = {
        scope: [
            {
                "board_name": str(row["板块名称"]),
                "board_code": str(row.get("板块代码", "") or ""),
                "board_type": scope,
                "selected": str(row["板块名称"]) in selected_names,
            }
            for _, row in df.iterrows()
        ]
    }
    return payload


def load_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        scope = "industry" if "industry" in path.stem else "concept"
        return default_payload(scope)
    return json.loads(path.read_text(encoding="utf-8"))


def save_payload(payload: Dict[str, Any], path: Path) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
