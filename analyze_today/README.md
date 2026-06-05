# Board Report Toolkit

这个目录现在以“概念/板块日报工具”为主，支持：

- 交互选择哪些概念、行业板块纳入分析
- 交互切换数据源：`akshare`、`eastmoney`、`ths`
- 生成表格化日报文件：`CSV + HTML`
- 输出板块分析指标、综合得分和基于 K 线的短线标签

## 主要文件

- [board_report_gui.py](/abs/path/c:/Users/Du/Desktop/analyze_today/board_report_gui.py)
  - 本地图形界面
- [board_report_daily.py](/abs/path/c:/Users/Du/Desktop/analyze_today/board_report_daily.py)
  - 命令行日报入口
- [board_report_core.py](/abs/path/c:/Users/Du/Desktop/analyze_today/board_report_core.py)
  - 数据源、配置、评分和导出逻辑
- [board_report_config.json](/abs/path/c:/Users/Du/Desktop/analyze_today/board_report_config.json)
  - 交互配置文件

原来的低 PE 相关脚本仍然保留，但不是这版 README 的重点。

## 安装依赖

建议 Python 3.11+。

```bash
pip install akshare pandas numpy requests py-mini-racer lxml html5lib
```

如果你要使用 `ths` 数据源，`py-mini-racer` 很重要，因为同花顺接口需要动态生成 `hexin-v`。

## 数据源说明

界面和命令行里都支持这三个 provider：

### `eastmoney`

- 通过 `AkShare` 调用东方财富相关板块接口
- 适合行业板块、概念板块、资金流、历史板块 K 线的统一获取
- 这是默认推荐源

### `akshare`

- 同样通过 `AkShare` 取数
- 在当前实现里，板块 universe、资金流和历史行情仍然主要走 AkShare 封装的东方财富接口
- 和 `eastmoney` 的区别主要在“你选择的口径名称”，便于后面继续扩展

### `ths`

- 使用同花顺概念/行业板块和同花顺历史指数
- 资金流也尝试走同花顺页面数据
- 当东方财富口径不稳定时可切到这个源

## 交互界面

运行：

```bash
python board_report_gui.py
```

界面里可以做这些事：

- 选择数据源
- 修改统计窗口 `lookback`
- 修改 HTML 日报各榜单展示条数 `topn`
- 修改每个板块请求之间的间隔 `sleep`
- 刷新“行业板块 / 概念板块”清单
- 双击“纳入分析”列，切换某个板块是否纳入分析
- 一键全选、全不选
- 保存配置
- 直接生成日报

### 使用顺序

1. 打开 `python board_report_gui.py`
2. 先选 provider
3. 点击“刷新板块清单”
4. 在“行业板块 / 概念板块”页签里双击切换“纳入分析”
5. 点击“保存配置”
6. 点击“生成日报”

## 命令行生成日报

如果你已经在 GUI 里选好了板块，平时可以直接跑：

```bash
python board_report_daily.py
```

常用参数：

```bash
python board_report_daily.py --provider eastmoney --lookback 20 --topn 12 --no-proxy
python board_report_daily.py --provider ths --lookback 30
```

参数说明：

- `--config`
  - 配置文件路径，默认 `board_report_config.json`
- `--out`
  - 输出目录，默认 `board_report_output`
- `--provider`
  - 临时覆盖配置里的数据源
- `--lookback`
  - 临时覆盖统计窗口
- `--topn`
  - 临时覆盖 HTML 榜单显示条数
- `--sleep`
  - 临时覆盖请求间隔
- `--no-proxy`
  - 清掉当前 shell 里的代理环境变量再抓数据

## 日报输出

默认输出到：

- `board_report_output/board_report_YYYYMMDD.csv`
- `board_report_output/board_report_YYYYMMDD.html`
- `board_report_output/board_report_config_snapshot_YYYYMMDD.json`

### CSV 字段

核心字段包括：

- `date`
- `provider`
- `board_type`
- `board_name`
- `board_code`
- `close`
- `pct_1d`
- `pct_5d`
- `pct_20d`
- `volume_ratio`
- `main_net_inflow_today`
- `main_net_ratio_today`
- `main_net_inflow_5d`
- `main_net_inflow_10d`
- `score`
- `label`

### HTML 内容

HTML 日报是表格形式，包含：

- 总表
- 行业板块表
- 概念板块表

适合盘后直接打开看。

## 评分与分析口径

当前日报会综合这些数据：

- 板块历史 K 线衍生涨跌幅
  - `1 日`
  - `5 日`
  - `20 日`
- 成交额放量倍数
  - 最新成交额 / 过去一段时间成交额中位数
- 资金流
  - 今日主力净流入
  - 今日主力净占比
  - 5 日主力净流入
  - 10 日主力净流入

综合得分 `score` 目前主要由这些项线性组合：

- `pct_1d`
- `pct_5d`
- `pct_20d`
- `main_net_ratio_today`
- `volume_ratio`

### 短线标签 `label`

根据涨跌幅、资金流和放量情况，会给出类似标签：

- `高位强趋势`
- `高位分歧`
- `短线加速`
- `低位启动`
- `低位吸金`
- `低位异动`
- `低位观察`
- `资金流出`
- `中性轮动`

## 配置文件结构

[board_report_config.json](/abs/path/c:/Users/Du/Desktop/analyze_today/board_report_config.json) 大致结构：

```json
{
  "meta": {
    "provider": "eastmoney",
    "lookback": 20,
    "topn": 12,
    "sleep": 0.15
  },
  "scopes": {
    "industry": {
      "selected_names": [],
      "board_catalog": []
    },
    "concept": {
      "selected_names": [],
      "board_catalog": []
    }
  }
}
```

其中：

- `selected_names`
  - 当前被纳入分析的板块名
- `board_catalog`
  - 刷新后抓到的全量板块清单
  - 每项都带 `selected` 开关

## 说明

- 这版工具重点是“交互选板块 + 多数据源 + 表格日报”
- 还没有把个股联动分析、板块成分股透视、图形 K 线截图一起做进去
- 若某个 provider 临时失效，优先切换到另一个源再跑

## 快速开始

```bash
python board_report_gui.py
```

或者：

```bash
python board_report_daily.py --provider eastmoney --no-proxy
```
