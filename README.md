For better reviewing the A-Share market
**工作流**

整个流程现在分成两步：

1. 先抓“可用板块总表”，生成一份你能改的配置文件
2. 再让日报脚本按这份配置文件去跑

核心文件是这几个：

- 配置文件：board_targets.json (line 1)
- 全量板块生成器：generate_board_config.py (line 1)
- 日报脚本：sector_daily_report.py (line 852)
- 相关股票脚本：sector_related_stocks.py (line 358)
- 共享配置逻辑：board_config.py (line 1)

**你平时怎么用**

先刷新全量板块：

powershell

`python generate_board_config.py --provider ths --no-proxy`

然后去改配置文件里的 target_groups：

- 这里决定 sector_daily_report 要跟踪哪些“目标板块”
- 每项可以改：
    - target：你自己定义的目标名
    - aliases：用于匹配真实板块名的别名
    - enabled：true/false，是否启用

再跑日报：

powershell

`python sector_daily_report.py --provider ths --no-proxy`

如果你要找某个目标板块下最相关的股票：

powershell

`python sector_related_stocks.py --target "化工" --no-proxy python sector_related_stocks.py --target "科技,金融" --topn 8 --no-proxy`

**配置文件结构**

board_targets.json 主要有两块：

- target_groups  
    这是你真正要维护的内容，按大类分组，比如 科技、金融、消费、化工、能源
- board_catalog  
    这是自动抓下来的“当前能抓到的全部板块参考清单”，方便你挑选和改别名

简单说：

- target_groups 决定“我要跟踪谁”
- board_catalog 告诉你“市场上现在能抓到谁”

**输入参数**

generate_board_config.py

- --provider {auto,akshare,ths}：选数据源
- --out：输出配置文件路径
- --no-proxy：忽略当前代理

sector_daily_report.py

- --out：日报输出目录，默认 ./sector_report
- --config：配置文件路径，默认 ./board_targets.json
- --lookback：统计窗口，默认 20
- --topn：每个榜单显示几条，默认 10
- --sleep：单板块抓取间隔
- --provider {auto,akshare,ths}
- --no-proxy

sector_related_stocks.py

- --target：输入一个或多个目标板块
- --topn：每个目标板块输出前几只股票
- --max-board-candidates：每个目标板块最多展开多少个候选真实板块
- --out：输出目录
- --config：配置文件路径
- --no-proxy

**运行时你会看到什么进度**

generate_board_config.py

- 清理代理
- 选择数据源
- 抓全量板块
- 写入 board_targets.json
- 打印板块总数

sector_daily_report.py

- 清理代理
- 选择数据源
- 读取配置文件
- 打印 板块 universe 数量
- 打印 配置中启用目标板块 数量
- 匹配目标板块
- 抓资金流
- 分析板块
- 输出 CSV / Markdown / 匹配表

sector_related_stocks.py

- 清理代理
- 读取配置文件
- 解析 --target
- 匹配候选真实板块
- 抓各候选板块成份股
- 算相关度
- 输出 CSV，并在终端打印前几条

**生成文件**

刷新板块配置后会生成：

- board_targets.json (line 1)

跑日报后会生成到 sector_report：

- sector_summary_20260520.csv
- sector_report_20260520.md
- board_match_20260520.csv

跑相关股票后会生成到同目录：

- sector_related_stocks_YYYYMMDD.csv

**推荐日常用法**

每天一般这样就够了：

powershell

`python generate_board_config.py --provider ths --no-proxy python sector_daily_report.py --provider ths --no-proxy python sector_related_stocks.py --target "科技,金融,消费" --topn 10 --no-proxy`

如果你不想每天刷新全量板块，也可以只在需要时更新一次 board_targets.json，平时直接跑日报。

**现在这套规则的重点**

- 你以后不需要再改源码里的板块列表
- 只改 board_targets.json
- sector_daily_report 和 sector_related_stocks 会共用同一套目标板块配置
- 当前大类归档是关键词规则分类，已经能用，但还可以继续细化
