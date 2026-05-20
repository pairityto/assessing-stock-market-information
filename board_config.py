#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import copy
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

import pandas as pd

DEFAULT_BOARD_CONFIG_PATH = Path("./board_targets.json")

DEFAULT_TARGET_GROUPS: Dict[str, List[Dict[str, Any]]] = {
    "科技": [
        {"target": "AI算力", "aliases": ["算力", "算力租赁", "东数西算", "人工智能", "AI算力"], "enabled": True},
        {"target": "光模块/光通信", "aliases": ["光模块", "光通信", "光器件", "通信设备"], "enabled": True},
        {"target": "CPO/硅光", "aliases": ["CPO", "共封装光学", "硅光", "硅光子"], "enabled": True},
        {"target": "PCB/CCL/电子布", "aliases": ["PCB", "印制电路板", "覆铜板", "CCL", "电子布"], "enabled": True},
        {"target": "AI服务器", "aliases": ["AI服务器", "服务器", "云计算", "数据中心"], "enabled": True},
        {"target": "液冷/数据中心温控", "aliases": ["液冷", "液冷服务器", "数据中心", "温控", "IDC"], "enabled": True},
        {"target": "算力租赁/IDC", "aliases": ["算力租赁", "IDC", "东数西算", "云计算"], "enabled": True},
        {"target": "半导体设备", "aliases": ["半导体设备", "芯片设备", "光刻机", "刻蚀机"], "enabled": True},
        {"target": "半导体材料", "aliases": ["半导体材料", "电子化学品", "光刻胶", "电子特气", "靶材", "CMP"], "enabled": True},
        {"target": "存储芯片", "aliases": ["存储芯片", "存储器", "DRAM", "HBM", "NAND"], "enabled": True},
        {"target": "长鑫/长江存储产业链", "aliases": ["长鑫", "长鑫存储", "长江存储", "存储芯片", "半导体"], "enabled": True},
        {"target": "先进封装/Chiplet", "aliases": ["先进封装", "Chiplet", "封装", "HBM"], "enabled": True},
        {"target": "封测/测试设备", "aliases": ["封测", "芯片封测", "测试设备", "半导体测试"], "enabled": True},
        {"target": "AI芯片/GPU/ASIC", "aliases": ["AI芯片", "GPU", "ASIC", "国产芯片", "芯片设计"], "enabled": True},
        {"target": "AIGC/生成式AI", "aliases": ["AIGC", "生成式AI", "ChatGPT", "文生视频", "文生图"], "enabled": True},
        {"target": "AI智能体/Agent", "aliases": ["AI智能体", "智能体", "Agent", "AI Agent", "数字员工"], "enabled": True},
        {"target": "多模态AI", "aliases": ["多模态AI", "多模态", "视觉语言模型", "VLM"], "enabled": True},
        {"target": "AI应用软件", "aliases": ["AI应用", "人工智能应用", "AI办公", "AI教育", "AI医疗", "软件开发"], "enabled": True},
        {"target": "大模型平台", "aliases": ["大模型", "模型平台", "通用大模型", "垂类大模型"], "enabled": True},
        {"target": "信创/国产软件", "aliases": ["信创", "国产软件", "操作系统", "数据库", "软件开发"], "enabled": True},
        {"target": "数据要素", "aliases": ["数据要素", "数据确权", "数据中心", "政务数据"], "enabled": True},
        {"target": "网络安全", "aliases": ["网络安全", "数据安全", "信息安全", "密码安全"], "enabled": True},
        {"target": "AI手机/AI PC/消费电子", "aliases": ["AI手机", "AI PC", "消费电子", "苹果概念", "智能穿戴"], "enabled": True},
        {"target": "MR/AR/VR", "aliases": ["MR", "AR", "VR", "虚拟现实", "增强现实", "混合现实"], "enabled": True},
    ],
    "先进制造": [
        {"target": "人形机器人", "aliases": ["人形机器人", "机器人", "机器视觉"], "enabled": True},
        {"target": "减速器/丝杠/电机/传感器", "aliases": ["减速器", "丝杠", "电机", "传感器", "伺服"], "enabled": True},
        {"target": "智能驾驶/车路云", "aliases": ["智能驾驶", "车路云", "无人驾驶", "V2X", "汽车电子"], "enabled": True},
        {"target": "低空经济/eVTOL", "aliases": ["低空经济", "eVTOL", "飞行汽车", "无人机"], "enabled": True},
        {"target": "卫星互联网/商业航天", "aliases": ["商业航天", "卫星互联网", "北斗导航", "军工电子"], "enabled": True},
    ],
    "金融": [
        {"target": "证券", "aliases": ["证券", "券商", "证券板块", "多元金融", "互联网金融", "证券行业"], "enabled": True},
    ],
    "消费": [
        {"target": "食品饮料/白酒", "aliases": ["食品饮料", "白酒", "啤酒", "乳业", "调味品", "饮料乳品", "休闲食品", "农产品加工"], "enabled": True},
        {"target": "医美美妆/美容护理", "aliases": ["美容护理", "医美", "医疗美容", "化妆品", "美妆", "个人护理", "护肤品"], "enabled": True},
        {"target": "商贸零售/奢侈品/旅游酒店", "aliases": ["商贸零售", "商业百货", "零售", "奢侈品", "珠宝首饰", "纺织服饰", "旅游酒店", "酒店餐饮", "免税店"], "enabled": True},
    ],
    "化工": [
        {"target": "化工", "aliases": ["化工", "基础化工", "化学原料", "化学制品", "化工原料", "化工行业"], "enabled": True},
        {"target": "PEEK材料", "aliases": ["PEEK", "peek材料", "工程塑料"], "enabled": True},
    ],
    "能源": [
        {"target": "固态电池/储能/新能源科技", "aliases": ["固态电池", "储能", "钠离子电池", "锂电池", "新能源"], "enabled": True},
    ],
}

CATEGORY_ORDER = [
    "科技",
    "金融",
    "消费",
    "化工",
    "能源",
    "医药",
    "先进制造",
    "地产基建",
    "资源周期",
    "公用事业",
    "农业食品",
    "交通物流",
    "传媒通信",
    "其他",
]

CATEGORY_RULES = [
    ("科技", ["ai", "算力", "光模块", "光通信", "cpo", "硅光", "pcb", "覆铜", "服务器", "半导体", "芯片", "封装", "封测", "信创", "软件", "数据", "网络安全", "消费电子", "ai手机", "ai pc", "mr", "ar", "vr"]),
    ("金融", ["证券", "券商", "银行", "保险", "金融", "多元金融"]),
    ("消费", ["白酒", "食品", "饮料", "乳业", "医美", "美容", "化妆品", "零售", "百货", "珠宝", "服饰", "旅游", "酒店", "餐饮", "免税", "奢侈"]),
    ("化工", ["化工", "化学", "材料", "塑料", "涂料", "农药", "化纤", "橡胶"]),
    ("能源", ["电池", "储能", "新能源", "光伏", "风电", "煤炭", "石油", "天然气", "电力"]),
    ("医药", ["医药", "医疗", "中药", "创新药", "生物", "器械"]),
    ("先进制造", ["机器人", "电机", "减速器", "丝杠", "传感器", "智能驾驶", "车路云", "无人驾驶", "低空", "evtol", "无人机", "航天", "卫星", "军工"]),
    ("地产基建", ["地产", "房地产", "基建", "建材", "建筑", "工程", "水泥"]),
    ("资源周期", ["有色", "钢铁", "稀土", "黄金", "铜", "铝", "锂矿", "煤化工"]),
    ("公用事业", ["公用事业", "环保", "燃气", "水务"]),
    ("农业食品", ["农业", "种业", "养殖", "渔业", "猪肉", "农产品"]),
    ("交通物流", ["物流", "航运", "港口", "机场", "快递", "铁路"]),
    ("传媒通信", ["传媒", "游戏", "影视", "广告", "通信", "运营商"]),
]


def _normalize_text(value: str) -> str:
    text = str(value or "").lower()
    return re.sub(r"[\s\-/（）()_]+", "", text)


def _deepcopy_groups(groups: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    return copy.deepcopy(groups)


def default_board_config() -> Dict[str, Any]:
    return {
        "meta": {
            "schema_version": 1,
            "generated_at": None,
            "source_provider": None,
            "description": "target_groups 可直接修改，board_catalog 为自动抓取的全量板块参考清单。",
        },
        "target_groups": _deepcopy_groups(DEFAULT_TARGET_GROUPS),
        "board_catalog": {category: [] for category in CATEGORY_ORDER},
    }


def _target_groups_from_flat_map(target_boards: Dict[str, List[str]]) -> Dict[str, List[Dict[str, Any]]]:
    groups = _deepcopy_groups(DEFAULT_TARGET_GROUPS)
    existing_targets = {entry["target"] for items in groups.values() for entry in items}
    for target, aliases in target_boards.items():
        if target in existing_targets:
            continue
        category = categorize_board_name(target)
        groups.setdefault(category, []).append({"target": target, "aliases": list(aliases), "enabled": True})
    return groups


def load_board_config(config_path: Path | str | None = None, fallback_targets: Dict[str, List[str]] | None = None) -> Dict[str, Any]:
    path = Path(config_path or DEFAULT_BOARD_CONFIG_PATH)
    if not path.exists():
        payload = default_board_config()
        if fallback_targets:
            payload["target_groups"] = _target_groups_from_flat_map(fallback_targets)
        return payload

    payload = json.loads(path.read_text(encoding="utf-8"))
    if "target_groups" not in payload:
        legacy_groups = payload.get("groups")
        if isinstance(legacy_groups, dict):
            payload["target_groups"] = legacy_groups
        else:
            payload["target_groups"] = _target_groups_from_flat_map(fallback_targets or DEFAULT_TARGET_BOARDS)
    if "board_catalog" not in payload:
        payload["board_catalog"] = {category: [] for category in CATEGORY_ORDER}
    return payload


def save_board_config(payload: Dict[str, Any], config_path: Path | str | None = None) -> Path:
    path = Path(config_path or DEFAULT_BOARD_CONFIG_PATH)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def iter_target_entries(payload: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    groups = payload.get("target_groups", {})
    for category, entries in groups.items():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, str):
                yield {"category": category, "target": entry, "aliases": [entry], "enabled": True}
                continue
            if not isinstance(entry, dict):
                continue
            target = str(entry.get("target") or "").strip()
            if not target:
                continue
            aliases = entry.get("aliases") or [target]
            aliases = [str(alias).strip() for alias in aliases if str(alias).strip()]
            if not aliases:
                aliases = [target]
            yield {
                "category": category,
                "target": target,
                "aliases": aliases,
                "enabled": bool(entry.get("enabled", True)),
            }


def load_target_boards(config_path: Path | str | None = None, fallback_targets: Dict[str, List[str]] | None = None) -> Dict[str, List[str]]:
    payload = load_board_config(config_path=config_path, fallback_targets=fallback_targets)
    return target_boards_from_payload(payload)


def target_boards_from_payload(payload: Dict[str, Any]) -> Dict[str, List[str]]:
    target_boards: Dict[str, List[str]] = {}
    for entry in iter_target_entries(payload):
        if not entry["enabled"]:
            continue
        target_boards[entry["target"]] = entry["aliases"]
    return target_boards


def categorize_board_name(board_name: str) -> str:
    normalized = _normalize_text(board_name)
    if not normalized:
        return "其他"
    for category, keywords in CATEGORY_RULES:
        if any(_normalize_text(keyword) in normalized for keyword in keywords):
            return category
    return "其他"


def build_board_catalog(universe: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {category: [] for category in CATEGORY_ORDER}
    if universe is None or universe.empty:
        return groups

    records = (
        universe.loc[:, [col for col in ["板块名称", "板块代码", "board_type"] if col in universe.columns]]
        .drop_duplicates()
        .sort_values(["板块名称", "board_type"], na_position="last")
        .to_dict("records")
    )
    for record in records:
        board_name = str(record.get("板块名称") or "").strip()
        if not board_name:
            continue
        category = categorize_board_name(board_name)
        item = {"board_name": board_name, "board_type": record.get("board_type", "")}
        board_code = record.get("板块代码")
        if board_code is not None and str(board_code).strip():
            item["board_code"] = str(board_code).strip()
        groups.setdefault(category, []).append(item)
    return groups


def build_board_config(universe: pd.DataFrame, provider: str, existing_payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = copy.deepcopy(existing_payload) if existing_payload else default_board_config()
    payload.setdefault("meta", {})
    payload["meta"].update(
        {
            "schema_version": 1,
            "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_provider": provider,
        }
    )
    payload.setdefault("target_groups", _deepcopy_groups(DEFAULT_TARGET_GROUPS))
    payload["board_catalog"] = build_board_catalog(universe)
    return payload


DEFAULT_TARGET_BOARDS = load_target_boards(fallback_targets={})
