# A股板块日报工具

这套工具现在默认采用`AkShare + 东方财富板块口径`，并拆成两套可独立维护的配置：

- `board_targets_ak_industry.json`
- `board_targets_ak_concept.json`

对应两个分析视角：

- `行业板块`
  - 更稳定，适合看行业轮动、结构强弱
- `概念板块`
  - 更新更快，适合看 AI、算力、AIDC、CPO、液冷、东数西算这类热点题材

## 当前推荐入口

- 生成两套配置：`generate_ak_board_configs.py`
- 生成双视角日报：`dual_board_daily_report.py`

## 环境

```powershell
C:\Users\Du\miniconda3\python.exe -m pip install -r requirements.txt
```

如果缺依赖，也可以单独安装：

```powershell
C:\Users\Du\miniconda3\python.exe -m pip install akshare pandas numpy requests tqdm
```

## 核心文件

- `ak_board_config.py`
  - AkShare 行业/概念配置构建逻辑
- `generate_ak_board_configs.py`
  - 根据当前 AkShare 板块列表生成两份配置 JSON
- `dual_board_daily_report.py`
  - 按行业板块和概念板块分别分析、分别排序，并输出总榜
- `sector_daily_report.py`
  - 原有单配置日报脚本，继续保留
- `sector_related_stocks.py`
  - 查某个目标板块的相关个股

## 第一次使用

### 1. 生成两份配置

```powershell
python .\generate_ak_board_configs.py --provider akshare --no-proxy
```

生成文件：

- `board_targets_ak_industry.json`
- `board_targets_ak_concept.json`

### 2. 再跑双视角日报

```powershell
python .\dual_board_daily_report.py --provider akshare --no-proxy
```

## 你平时主要改哪里

通常不需要手改大量 JSON，先改生成器生成出来的配置文件里的：

- `analysis_selection.exact_names`
- `analysis_selection.include_keywords`
- `analysis_selection.exclude_keywords`

### 行业板块配置

文件：

- `board_targets_ak_industry.json`

作用：

- 选择你今天要看的行业板块
- 例如：`半导体`、`证券`、`通信设备`、`软件开发`

规则：

- `exact_names`
  - 精确选中的板块名
- `include_keywords`
  - 按关键词批量选板块
- `exclude_keywords`
  - 从已选结果里剔除

### 概念板块配置

文件：

- `board_targets_ak_concept.json`

作用：

- 选择你今天要看的热点概念
- 例如：`算力概念`、`东数西算`、`数据中心`、`液冷服务器`、`CPO概念`、`AI智能体`

规则同上：

- `exact_names`
- `include_keywords`
- `exclude_keywords`

## 板块分析逻辑

日报会对两类板块分别做以下分析：

- 历史 K 线
  - `1日涨跌幅`
  - `5日涨跌幅`
  - `20日涨跌幅`
- 成交活跃度
  - `成交额放量倍数`
- 资金流
  - `主力净流入_今日`
  - `主力净流入_5日`
  - `主力净流入_10日`
  - `主力净占比_今日%`
- 综合打分
  - `景气度分`
- 标签
  - `低位启动`
  - `短线加速`
  - `高位强趋势`
  - `资金流出/弱势`

## 输出结果

运行：

```powershell
python .\dual_board_daily_report.py --provider akshare --no-proxy
```

默认会生成：

- `sector_report\industry_summary_YYYYMMDD.csv`
- `sector_report\industry_match_YYYYMMDD.csv`
- `sector_report\concept_summary_YYYYMMDD.csv`
- `sector_report\concept_match_YYYYMMDD.csv`
- `sector_report\board_dual_summary_YYYYMMDD.csv`
- `sector_report\board_dual_report_YYYYMMDD.md`

其中：

- `industry_summary`
  - 行业板块单独排序结果
- `concept_summary`
  - 概念板块单独排序结果
- `board_dual_summary`
  - 行业 + 概念合并总榜
- `board_dual_report`
  - Markdown 版日报

## 推荐日常流程

### 每天盘后

```powershell
python .\generate_ak_board_configs.py --provider akshare --no-proxy
python .\dual_board_daily_report.py --provider akshare --no-proxy
```

### 只看热点 AI 主题

去改：

- `board_targets_ak_concept.json`

把这些放进 `exact_names` 或 `include_keywords`：

- `算力`
- `东数西算`
- `数据中心`
- `AIDC`
- `液冷`
- `CPO`
- `AI智能体`
- `AI芯片`
- `AIGC`

### 只看稳定行业

去改：

- `board_targets_ak_industry.json`

例如保留：

- `半导体`
- `证券`
- `通信设备`
- `软件开发`
- `自动化设备`

## 和旧版配置的关系

仓库里原来的这些文件仍保留：

- `board_targets.json`
- `sw_board_config.py`
- `csi_board_config.py`

但当前默认推荐路线已经切换为：

- `AkShare 行业板块配置`
- `AkShare 概念板块配置`
- `双视角日报`
