#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

OUTPUT_PATH = Path(__file__).with_name("board_targets_sw_2021.json")

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
    {"key": "turnover_rate", "name": "换手率", "group": "量能", "description": "板块成分股换手情况"},
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

SW_2021_INDUSTRIES: Dict[str, List[Dict[str, Any]]] = {
    "农林牧渔": [
        {"level2": "种植业", "enabled": True, "aliases": ["种植业", "种子", "粮食种植"]},
        {"level2": "渔业", "enabled": True, "aliases": ["渔业", "海洋捕捞", "水产养殖"]},
        {"level2": "林业", "enabled": True, "aliases": ["林业"]},
        {"level2": "饲料", "enabled": True, "aliases": ["饲料", "畜禽饲料", "宠物食品"]},
        {"level2": "农产品加工", "enabled": True, "aliases": ["农产品加工", "果蔬加工", "粮油加工"]},
        {"level2": "养殖业", "enabled": True, "aliases": ["养殖业", "生猪养殖", "肉鸡养殖"]},
        {"level2": "动物保健", "enabled": True, "aliases": ["动物保健"]},
    ],
    "基础化工": [
        {"level2": "化学原料", "enabled": True, "aliases": ["化学原料", "纯碱", "氯碱", "无机盐"]},
        {"level2": "化学制品", "enabled": True, "aliases": ["化学制品", "氟化工", "聚氨酯", "有机硅", "化工"]},
        {"level2": "化学纤维", "enabled": True, "aliases": ["化学纤维", "涤纶", "粘胶", "氨纶"]},
        {"level2": "塑料", "enabled": True, "aliases": ["塑料", "改性塑料", "膜材料"]},
        {"level2": "橡胶", "enabled": True, "aliases": ["橡胶", "炭黑", "轮胎"]},
        {"level2": "农化制品", "enabled": True, "aliases": ["农化制品", "农药", "磷肥及磷化工", "钾肥", "复合肥"]},
        {"level2": "非金属材料", "enabled": True, "aliases": ["非金属材料"]},
    ],
    "钢铁": [
        {"level2": "普钢", "enabled": True, "aliases": ["普钢", "长材", "板材", "钢铁管材"]},
        {"level2": "特钢", "enabled": True, "aliases": ["特钢"]},
    ],
    "有色金属": [
        {"level2": "金属新材料", "enabled": True, "aliases": ["金属新材料", "磁性材料"]},
        {"level2": "工业金属", "enabled": True, "aliases": ["工业金属", "铜", "铝", "铅锌"]},
        {"level2": "贵金属", "enabled": True, "aliases": ["贵金属", "黄金", "白银"]},
        {"level2": "小金属", "enabled": True, "aliases": ["小金属", "稀土", "钨", "钼"]},
        {"level2": "能源金属", "enabled": True, "aliases": ["能源金属", "锂", "钴", "镍"]},
    ],
    "电子": [
        {"level2": "半导体", "enabled": True, "aliases": ["半导体", "芯片", "存储", "封测", "半导体设备"]},
        {"level2": "元件", "enabled": True, "aliases": ["元件", "印制电路板", "PCB", "被动元件"]},
        {"level2": "光学光电子", "enabled": True, "aliases": ["光学光电子", "面板", "LED", "光学元件"]},
        {"level2": "其他电子", "enabled": True, "aliases": ["其他电子"]},
        {"level2": "消费电子", "enabled": True, "aliases": ["消费电子", "品牌消费电子", "消费电子零部件及组装"]},
        {"level2": "电子化学品", "enabled": True, "aliases": ["电子化学品"]},
    ],
    "汽车": [
        {"level2": "汽车零部件", "enabled": True, "aliases": ["汽车零部件", "汽配", "轮胎轮毂", "汽车电子电气系统"]},
        {"level2": "汽车服务", "enabled": True, "aliases": ["汽车服务", "汽车经销商"]},
        {"level2": "摩托车及其他", "enabled": True, "aliases": ["摩托车及其他", "摩托车", "其他运输设备"]},
        {"level2": "乘用车", "enabled": True, "aliases": ["乘用车", "电动乘用车", "综合乘用车"]},
        {"level2": "商用车", "enabled": True, "aliases": ["商用车", "商用载货车", "商用载客车"]},
    ],
    "家用电器": [
        {"level2": "白色家电", "enabled": True, "aliases": ["白色家电", "空调", "冰洗"]},
        {"level2": "黑色家电", "enabled": True, "aliases": ["黑色家电", "彩电"]},
        {"level2": "小家电", "enabled": True, "aliases": ["小家电", "厨房小家电", "清洁小家电", "个护小家电"]},
        {"level2": "厨卫电器", "enabled": True, "aliases": ["厨卫电器", "厨房电器", "卫浴电器"]},
        {"level2": "照明设备", "enabled": True, "aliases": ["照明设备"]},
        {"level2": "家电零部件", "enabled": True, "aliases": ["家电零部件"]},
        {"level2": "其他家电", "enabled": True, "aliases": ["其他家电"]},
    ],
    "食品饮料": [
        {"level2": "食品加工", "enabled": True, "aliases": ["食品加工", "肉制品", "保健品", "预加工食品", "其他食品"]},
        {"level2": "白酒", "enabled": True, "aliases": ["白酒"]},
        {"level2": "非白酒", "enabled": True, "aliases": ["非白酒", "啤酒", "其他酒类"]},
        {"level2": "饮料乳品", "enabled": True, "aliases": ["饮料乳品", "软饮料", "乳品"]},
        {"level2": "休闲食品", "enabled": True, "aliases": ["休闲食品", "零食", "烘焙食品", "熟食"]},
        {"level2": "调味发酵品", "enabled": True, "aliases": ["调味发酵品"]},
    ],
    "纺织服饰": [
        {"level2": "纺织制造", "enabled": True, "aliases": ["纺织制造", "棉纺", "印染"]},
        {"level2": "服装家纺", "enabled": True, "aliases": ["服装家纺", "男装", "女装", "家纺"]},
        {"level2": "饰品", "enabled": True, "aliases": ["饰品", "钟表珠宝", "奢侈品"]},
    ],
    "轻工制造": [
        {"level2": "造纸", "enabled": True, "aliases": ["造纸", "特种纸", "生活用纸"]},
        {"level2": "包装印刷", "enabled": True, "aliases": ["包装印刷", "包装", "印刷"]},
        {"level2": "家居用品", "enabled": True, "aliases": ["家居用品", "定制家居", "成品家居", "卫浴制品"]},
        {"level2": "文娱用品", "enabled": True, "aliases": ["文娱用品"]},
    ],
    "医药生物": [
        {"level2": "化学制药", "enabled": True, "aliases": ["化学制药", "原料药", "化学制剂"]},
        {"level2": "中药", "enabled": True, "aliases": ["中药"]},
        {"level2": "生物制品", "enabled": True, "aliases": ["生物制品", "血液制品", "疫苗"]},
        {"level2": "医疗器械", "enabled": True, "aliases": ["医疗器械", "医疗设备", "医疗耗材", "体外诊断"]},
        {"level2": "医疗服务", "enabled": True, "aliases": ["医疗服务", "医院", "诊断服务", "CXO", "医疗研发外包"]},
        {"level2": "医药商业", "enabled": True, "aliases": ["医药商业", "医药流通", "互联网药店", "线下药店"]},
    ],
    "公用事业": [
        {"level2": "电力", "enabled": True, "aliases": ["电力", "火电", "水电", "核电", "风力发电", "光伏发电"]},
        {"level2": "燃气", "enabled": True, "aliases": ["燃气"]},
        {"level2": "电能综合服务", "enabled": True, "aliases": ["电能综合服务"]},
    ],
    "交通运输": [
        {"level2": "铁路公路", "enabled": True, "aliases": ["铁路公路", "高速公路"]},
        {"level2": "公交", "enabled": True, "aliases": ["公交"]},
        {"level2": "港口航运", "enabled": True, "aliases": ["港口航运", "港口", "航运"]},
        {"level2": "航空机场", "enabled": True, "aliases": ["航空机场", "机场", "航空运输"]},
        {"level2": "物流", "enabled": True, "aliases": ["物流", "快递", "仓储物流", "跨境物流"]},
        {"level2": "铁路运输", "enabled": True, "aliases": ["铁路运输"]},
    ],
    "房地产": [
        {"level2": "房地产开发", "enabled": True, "aliases": ["房地产开发", "住宅开发", "商业地产"]},
        {"level2": "房地产服务", "enabled": True, "aliases": ["房地产服务", "物业管理", "房产租赁经纪"]},
    ],
    "商贸零售": [
        {"level2": "一般零售", "enabled": True, "aliases": ["一般零售", "百货", "超市", "连锁"]},
        {"level2": "专业连锁", "enabled": True, "aliases": ["专业连锁"]},
        {"level2": "互联网电商", "enabled": True, "aliases": ["互联网电商", "综合电商", "跨境电商", "电商服务"]},
        {"level2": "旅游零售", "enabled": True, "aliases": ["旅游零售", "免税"]},
    ],
    "社会服务": [
        {"level2": "景点及旅游", "enabled": True, "aliases": ["景点及旅游", "旅游"]},
        {"level2": "酒店餐饮", "enabled": True, "aliases": ["酒店餐饮", "酒店", "餐饮"]},
        {"level2": "教育", "enabled": True, "aliases": ["教育"]},
        {"level2": "体育", "enabled": True, "aliases": ["体育"]},
        {"level2": "本地生活服务", "enabled": True, "aliases": ["本地生活服务"]},
        {"level2": "专业服务", "enabled": True, "aliases": ["专业服务", "人力资源服务", "检测服务", "会展服务"]},
    ],
    "综合": [
        {"level2": "综合", "enabled": True, "aliases": ["综合"]},
    ],
    "建筑材料": [
        {"level2": "水泥", "enabled": True, "aliases": ["水泥", "水泥制造", "水泥制品"]},
        {"level2": "玻璃玻纤", "enabled": True, "aliases": ["玻璃玻纤", "玻璃", "玻纤"]},
        {"level2": "装修建材", "enabled": True, "aliases": ["装修建材", "管材", "防水材料", "涂料"]},
    ],
    "建筑装饰": [
        {"level2": "房屋建设", "enabled": True, "aliases": ["房屋建设"]},
        {"level2": "基础建设", "enabled": True, "aliases": ["基础建设", "基建"]},
        {"level2": "专业工程", "enabled": True, "aliases": ["专业工程", "钢结构", "园林工程"]},
        {"level2": "工程咨询服务", "enabled": True, "aliases": ["工程咨询服务"]},
    ],
    "电力设备": [
        {"level2": "电机", "enabled": True, "aliases": ["电机"]},
        {"level2": "电网设备", "enabled": True, "aliases": ["电网设备", "输变电设备"]},
        {"level2": "其他电源设备", "enabled": True, "aliases": ["其他电源设备"]},
        {"level2": "光伏设备", "enabled": True, "aliases": ["光伏设备", "硅料硅片", "逆变器", "光伏辅材"]},
        {"level2": "风电设备", "enabled": True, "aliases": ["风电设备", "风电整机", "风电零部件"]},
        {"level2": "电池", "enabled": True, "aliases": ["电池", "锂电池", "电池化学品", "燃料电池"]},
    ],
    "机械设备": [
        {"level2": "通用设备", "enabled": True, "aliases": ["通用设备", "机床工具", "制冷空调设备"]},
        {"level2": "专用设备", "enabled": True, "aliases": ["专用设备", "半导体设备", "锂电设备"]},
        {"level2": "轨交设备", "enabled": True, "aliases": ["轨交设备"]},
        {"level2": "工程机械", "enabled": True, "aliases": ["工程机械", "工程机械整机", "工程机械器件"]},
        {"level2": "自动化设备", "enabled": True, "aliases": ["自动化设备", "机器人", "工控设备", "激光设备"]},
    ],
    "国防军工": [
        {"level2": "航空装备", "enabled": True, "aliases": ["航空装备"]},
        {"level2": "航海装备", "enabled": True, "aliases": ["航海装备"]},
        {"level2": "地面兵装", "enabled": True, "aliases": ["地面兵装"]},
        {"level2": "航天装备", "enabled": True, "aliases": ["航天装备"]},
        {"level2": "军工电子", "enabled": True, "aliases": ["军工电子"]},
        {"level2": "军工材料", "enabled": True, "aliases": ["军工材料"]},
    ],
    "计算机": [
        {"level2": "软件开发", "enabled": True, "aliases": ["软件开发", "工业软件", "应用软件", "基础软件"]},
        {"level2": "IT服务", "enabled": True, "aliases": ["IT服务", "云计算", "数据中心", "系统集成"]},
        {"level2": "计算机设备", "enabled": True, "aliases": ["计算机设备", "服务器", "安防设备"]},
    ],
    "通信": [
        {"level2": "通信设备", "enabled": True, "aliases": ["通信设备", "光模块", "交换设备", "无线通信设备"]},
        {"level2": "通信服务", "enabled": True, "aliases": ["通信服务", "通信工程及服务", "通信应用增值服务", "运营商"]},
    ],
    "银行": [
        {"level2": "国有大型银行", "enabled": True, "aliases": ["国有大型银行"]},
        {"level2": "股份制银行", "enabled": True, "aliases": ["股份制银行"]},
        {"level2": "城商行", "enabled": True, "aliases": ["城商行"]},
        {"level2": "农商行", "enabled": True, "aliases": ["农商行"]},
        {"level2": "其他银行", "enabled": True, "aliases": ["其他银行"]},
    ],
    "非银金融": [
        {"level2": "证券", "enabled": True, "aliases": ["证券", "券商", "投行"]},
        {"level2": "保险", "enabled": True, "aliases": ["保险"]},
        {"level2": "多元金融", "enabled": True, "aliases": ["多元金融", "期货", "信托", "租赁", "金融信息服务", "资产管理"]},
    ],
    "传媒": [
        {"level2": "游戏", "enabled": True, "aliases": ["游戏"]},
        {"level2": "社交", "enabled": True, "aliases": ["社交"]},
        {"level2": "数字媒体", "enabled": True, "aliases": ["数字媒体", "视频媒体", "音频媒体", "门户网站"]},
        {"level2": "广告营销", "enabled": True, "aliases": ["广告营销", "营销代理", "广告媒体"]},
        {"level2": "影视院线", "enabled": True, "aliases": ["影视院线", "影视动漫制作", "院线"]},
        {"level2": "出版", "enabled": True, "aliases": ["出版", "教育出版", "大众出版"]},
        {"level2": "电视广播", "enabled": True, "aliases": ["电视广播"]},
    ],
    "煤炭": [
        {"level2": "煤炭开采", "enabled": True, "aliases": ["煤炭开采", "动力煤", "焦煤"]},
        {"level2": "焦炭", "enabled": True, "aliases": ["焦炭"]},
    ],
    "石油石化": [
        {"level2": "油气开采", "enabled": True, "aliases": ["油气开采"]},
        {"level2": "油服工程", "enabled": True, "aliases": ["油服工程", "油田服务", "油气及炼化工程"]},
        {"level2": "炼化及贸易", "enabled": True, "aliases": ["炼化及贸易", "炼油化工", "油品石化贸易"]},
    ],
    "环保": [
        {"level2": "环境治理", "enabled": True, "aliases": ["环境治理", "大气治理", "水务及水治理", "固废治理"]},
        {"level2": "环保设备", "enabled": True, "aliases": ["环保设备"]},
    ],
    "美容护理": [
        {"level2": "个护用品", "enabled": True, "aliases": ["个护用品", "生活用纸", "洗护用品"]},
        {"level2": "化妆品", "enabled": True, "aliases": ["化妆品", "品牌化妆品"]},
        {"level2": "医疗美容", "enabled": True, "aliases": ["医疗美容", "医美耗材", "医美服务"]},
    ],
}

ANALYSIS_PARAMETERS: Dict[str, Any] = {
    "description": "修改 include_level1 / include_level2 / exclude_level2 后，重新运行本文件即可刷新今日分析配置。",
    "include_level1": [
        "电子",
        "计算机",
        "通信",
        "非银金融",
    ],
    "include_level2": [],
    "exclude_level2": [],
    "lookback_days": 60,
    "moving_average_windows": [5, 10, 20, 60],
    "topn": 10,
    "matching_mode": "sw_level2_alias_first",
}


def build_target_groups() -> Dict[str, List[Dict[str, Any]]]:
    include_level1 = set(ANALYSIS_PARAMETERS.get("include_level1", []))
    include_level2 = set(ANALYSIS_PARAMETERS.get("include_level2", []))
    exclude_level2 = set(ANALYSIS_PARAMETERS.get("exclude_level2", []))

    target_groups: Dict[str, List[Dict[str, Any]]] = {}
    for level1, items in SW_2021_INDUSTRIES.items():
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
            "schema_version": 3,
            "generated_by": "sw_board_config.py",
            "classification_standard": "申万行业分类标准2021版",
            "industry_levels": {"level1": 31},
            "notes": [
                "本文件按申万2021版一级行业组织，并提供常用二级行业筛选模板。",
                "today_analysis 通过 include_level1 / include_level2 / exclude_level2 控制今日分析范围。",
                "target_groups 已按筛选结果自动展开，可直接给 sector_daily_report.py 的 --config 使用。",
            ],
        },
        "today_analysis": ANALYSIS_PARAMETERS,
        "kline_read_fields": KLINE_READ_FIELDS,
        "sw_2021_industry_structure": SW_2021_INDUSTRIES,
        "target_groups": build_target_groups(),
        "board_catalog": {level1: [] for level1 in SW_2021_INDUSTRIES},
    }


def save_payload(path: Path = OUTPUT_PATH) -> Path:
    payload = build_payload()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    path = save_payload()
    total_level1 = len(SW_2021_INDUSTRIES)
    total_level2 = sum(len(items) for items in SW_2021_INDUSTRIES.values())
    total_selected = sum(len(items) for items in build_target_groups().values())
    print(f"[OK] 已生成申万行业配置: {path}")
    print(f"[INFO] 一级行业: {total_level1}")
    print(f"[INFO] 模板内二级行业: {total_level2}")
    print(f"[INFO] 今日分析已选二级行业: {total_selected}")


if __name__ == "__main__":
    main()
