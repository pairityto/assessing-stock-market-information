#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

OUTPUT_PATH = Path(__file__).with_name("board_targets_csi.json")


KLINE_READ_FIELDS: List[Dict[str, str]] = [
    {"key": "date", "name": "交易日期", "group": "基础", "description": "板块K线对应的交易日"},
    {"key": "open", "name": "开盘价", "group": "K线", "description": "当日开盘价"},
    {"key": "high", "name": "最高价", "group": "K线", "description": "当日最高价"},
    {"key": "low", "name": "最低价", "group": "K线", "description": "当日最低价"},
    {"key": "close", "name": "收盘价", "group": "K线", "description": "当日收盘价"},
    {"key": "pct_change", "name": "涨跌幅", "group": "K线", "description": "相对前一交易日收盘价的涨跌幅"},
    {"key": "amplitude", "name": "振幅", "group": "K线", "description": "(最高价-最低价)/前收盘价"},
    {"key": "volume", "name": "成交量", "group": "量能", "description": "成交股数或成交份额"},
    {"key": "amount", "name": "成交额", "group": "量能", "description": "成交金额"},
    {"key": "turnover_rate", "name": "换手率", "group": "量能", "description": "板块成分股自由流通换手情况"},
    {"key": "volume_ratio", "name": "量比", "group": "量能", "description": "相对近期平均成交量的活跃度"},
    {"key": "ma5", "name": "MA5", "group": "均线", "description": "5日均线"},
    {"key": "ma10", "name": "MA10", "group": "均线", "description": "10日均线"},
    {"key": "ma20", "name": "MA20", "group": "均线", "description": "20日均线"},
    {"key": "ma60", "name": "MA60", "group": "均线", "description": "60日均线"},
    {"key": "macd", "name": "MACD", "group": "动量", "description": "趋势动量指标"},
    {"key": "rsi", "name": "RSI", "group": "动量", "description": "相对强弱指标"},
    {"key": "kdj", "name": "KDJ", "group": "动量", "description": "随机指标"},
    {"key": "main_net_inflow", "name": "主力净流入", "group": "资金", "description": "主力资金净流入/净流出"},
    {"key": "super_large_order_net", "name": "超大单净额", "group": "资金", "description": "超大单净流入/净流出"},
    {"key": "large_order_net", "name": "大单净额", "group": "资金", "description": "大单净流入/净流出"},
    {"key": "up_count", "name": "上涨家数", "group": "广度", "description": "板块内上涨成分股数量"},
    {"key": "down_count", "name": "下跌家数", "group": "广度", "description": "板块内下跌成分股数量"},
    {"key": "limit_up_count", "name": "涨停家数", "group": "广度", "description": "板块内涨停股数量"},
    {"key": "limit_down_count", "name": "跌停家数", "group": "广度", "description": "板块内跌停股数量"},
]


CSI_INDUSTRIES: Dict[str, List[Dict[str, Any]]] = {
    "能源": [
        {"level2": "能源设备与服务", "enabled": True, "aliases": ["能源设备与服务", "能源设备", "油服工程", "油气服务"]},
        {"level2": "石油天然气与消费用燃料", "enabled": True, "aliases": ["石油天然气与消费用燃料", "石油石化", "油气开采", "炼化", "煤炭", "燃气"]},
    ],
    "原材料": [
        {"level2": "化学制品", "enabled": True, "aliases": ["化学制品", "基础化工", "化工", "化学原料"]},
        {"level2": "建筑材料", "enabled": True, "aliases": ["建筑材料", "建材", "水泥", "玻纤", "装修建材"]},
        {"level2": "金属与采矿", "enabled": True, "aliases": ["金属与采矿", "有色金属", "钢铁", "黄金", "稀土", "铜", "铝", "锂矿"]},
        {"level2": "纸类与林业产品", "enabled": True, "aliases": ["纸类与林业产品", "造纸", "纸业", "林业"]},
    ],
    "工业": [
        {"level2": "资本品", "enabled": True, "aliases": ["资本品", "建筑与工程", "专用设备", "通用设备", "工程机械"]},
        {"level2": "商业服务与用品", "enabled": True, "aliases": ["商业服务与用品", "检测服务", "环保服务", "广告营销", "人力服务"]},
        {"level2": "运输", "enabled": True, "aliases": ["运输", "物流", "航运", "港口", "机场", "铁路公路"]},
        {"level2": "国防军工", "enabled": True, "aliases": ["国防军工", "军工", "航天装备", "船舶制造"]},
        {"level2": "电气设备", "enabled": True, "aliases": ["电气设备", "电网设备", "输变电", "风电设备", "光伏设备"]},
        {"level2": "机械制造", "enabled": True, "aliases": ["机械制造", "机器人", "自动化设备", "轨交设备"]},
    ],
    "可选消费": [
        {"level2": "汽车与汽车零部件", "enabled": True, "aliases": ["汽车与汽车零部件", "汽车整车", "汽车零部件", "汽配", "商用车"]},
        {"level2": "耐用消费品与服装", "enabled": True, "aliases": ["耐用消费品与服装", "家电", "家具", "家居用品", "纺织服饰"]},
        {"level2": "消费者服务", "enabled": True, "aliases": ["消费者服务", "旅游酒店", "教育", "休闲服务", "餐饮"]},
        {"level2": "零售业", "enabled": True, "aliases": ["零售业", "商贸零售", "百货", "连锁零售", "免税"]},
        {"level2": "休闲设备与产品", "enabled": True, "aliases": ["休闲设备与产品", "文娱用品", "体育用品", "玩具", "摩托车"]},
    ],
    "主要消费": [
        {"level2": "食品饮料烟草", "enabled": True, "aliases": ["食品饮料烟草", "食品饮料", "白酒", "啤酒", "乳业", "调味品", "烟草"]},
        {"level2": "家庭与个人用品", "enabled": True, "aliases": ["家庭与个人用品", "美容护理", "个护", "家清用品", "化妆品"]},
        {"level2": "食品与主要用品零售", "enabled": True, "aliases": ["食品与主要用品零售", "超市", "连锁商超", "便利店"]},
        {"level2": "农产品", "enabled": True, "aliases": ["农产品", "种植业", "养殖业", "农产品加工", "饲料"]},
    ],
    "医药卫生": [
        {"level2": "医疗保健设备与服务", "enabled": True, "aliases": ["医疗保健设备与服务", "医疗器械", "医疗服务", "医院", "体外诊断"]},
        {"level2": "制药生物科技与生命科学", "enabled": True, "aliases": ["制药生物科技与生命科学", "化学制药", "中药", "生物制品", "创新药", "CXO"]},
    ],
    "金融": [
        {"level2": "银行", "enabled": True, "aliases": ["银行"]},
        {"level2": "多元金融", "enabled": True, "aliases": ["多元金融", "金融科技", "信托", "租赁", "消费金融"]},
        {"level2": "保险", "enabled": True, "aliases": ["保险"]},
        {"level2": "资本市场", "enabled": True, "aliases": ["资本市场", "证券", "券商", "期货", "投行"]},
    ],
    "信息技术": [
        {"level2": "软件与服务", "enabled": True, "aliases": ["软件与服务", "计算机应用", "IT服务", "云计算", "工业软件", "AIGC"]},
        {"level2": "技术硬件与设备", "enabled": True, "aliases": ["技术硬件与设备", "消费电子", "计算机设备", "通信设备", "服务器"]},
        {"level2": "半导体与半导体生产设备", "enabled": True, "aliases": ["半导体与半导体生产设备", "半导体", "芯片", "存储", "封测", "半导体设备"]},
        {"level2": "电子设备仪器和元件", "enabled": True, "aliases": ["电子设备仪器和元件", "电子元件", "PCB", "被动元件", "光模块", "CPO"]},
    ],
    "通信服务": [
        {"level2": "电信服务", "enabled": True, "aliases": ["电信服务", "通信服务", "运营商", "IDC", "卫星通信"]},
        {"level2": "媒体与娱乐", "enabled": True, "aliases": ["媒体与娱乐", "游戏", "影视", "出版", "社交媒体"]},
    ],
    "公用事业": [
        {"level2": "公用事业", "enabled": True, "aliases": ["公用事业", "电力", "燃气", "水务", "环保运营", "核电"]},
    ],
    "房地产": [
        {"level2": "房地产管理和开发", "enabled": True, "aliases": ["房地产管理和开发", "房地产", "物业管理", "园区开发", "REITs"]},
    ],
}


ANALYSIS_PARAMETERS: Dict[str, Any] = {
    "description": "修改 include_level1 / include_level2 / exclude_level2 后，重新运行本文件即可刷新今日分析配置。",
    "include_level1": [
        "信息技术",
        "通信服务",
        "金融",
    ],
    "include_level2": [
        "半导体与半导体生产设备",
        "电子设备仪器和元件",
        "软件与服务",
        "资本市场",
    ],
    "exclude_level2": [],
    "lookback_days": 60,
    "moving_average_windows": [5, 10, 20, 60],
    "topn": 10,
    "matching_mode": "level2_alias_first",
}


def build_target_groups() -> Dict[str, List[Dict[str, Any]]]:
    include_level1 = set(ANALYSIS_PARAMETERS.get("include_level1", []))
    include_level2 = set(ANALYSIS_PARAMETERS.get("include_level2", []))
    exclude_level2 = set(ANALYSIS_PARAMETERS.get("exclude_level2", []))

    target_groups: Dict[str, List[Dict[str, Any]]] = {}
    for level1, items in CSI_INDUSTRIES.items():
        if include_level1 and level1 not in include_level1:
            continue

        selected_items: List[Dict[str, Any]] = []
        for item in items:
            level2 = item["level2"]
            if not item.get("enabled", True):
                continue
            if include_level2 and level2 not in include_level2:
                continue
            if level2 in exclude_level2:
                continue
            selected_items.append(
                {
                    "target": level2,
                    "aliases": item.get("aliases", [level2]),
                    "enabled": True,
                }
            )
        if selected_items:
            target_groups[level1] = selected_items
    return target_groups


def build_payload() -> Dict[str, Any]:
    return {
        "meta": {
            "schema_version": 2,
            "generated_by": "csi_board_config.py",
            "classification_standard": "中证行业分类标准说明（2025年11月版）",
            "industry_levels": {"level1": 11, "level2": 35},
            "notes": [
                "本文件在现有 board_targets.json 之外单独生成，避免覆盖你原来的热点板块配置。",
                "today_analysis 通过 include_level1 / include_level2 / exclude_level2 控制今日分析范围。",
                "target_groups 已按上述筛选结果自动展开，可直接给 sector_daily_report.py 的 --config 使用。",
            ],
        },
        "today_analysis": ANALYSIS_PARAMETERS,
        "kline_read_fields": KLINE_READ_FIELDS,
        "csi_industry_structure": CSI_INDUSTRIES,
        "target_groups": build_target_groups(),
        "board_catalog": {level1: [] for level1 in CSI_INDUSTRIES},
    }


def save_payload(path: Path = OUTPUT_PATH) -> Path:
    payload = build_payload()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    path = save_payload()
    total_level2 = sum(len(items) for items in CSI_INDUSTRIES.values())
    total_selected = sum(len(items) for items in build_target_groups().values())
    print(f"[OK] 已生成中证行业配置: {path}")
    print(f"[INFO] 一级行业: {len(CSI_INDUSTRIES)}")
    print(f"[INFO] 二级行业: {total_level2}")
    print(f"[INFO] 今日分析已选二级行业: {total_selected}")


if __name__ == "__main__":
    main()
