# SKILL: csi300PEstrategy 量化交易框架完整指南

## 0. 项目概述

**csi300PEstrategy** 是一个全链路量化策略开发框架，包括：
- 📊 **数据管理层**：多源数据获取、清洗、存储（get_data.py）
- 🔬 **因子计算层**：技术指标、Alpha因子计算（alpha.py）
- 📈 **策略层**：策略基类、信号生成、风控逻辑（strategy.py）
- 🔄 **回测层**：单策略回测、结果分析（backtest.py, lowpe_backtest.py）

### 目录结构
```
csi300PEstrategy/
├── get_data.py              # 数据下载、清洗、保存
├── alpha.py                 # Alpha因子与技术指标计算
├── warmup.py                # 数据预热（批量计算指标）
├── strategy.py              # 策略基类与具体策略实现
├── backtest.py              # 通用回测框架基类
├── lowpe_backtest.py        # 低PE策略专用回测类
├── copylimitBackTest.py     # 原始回测框架参考（已弃用）
└── data/
    ├── CN_Index/daily/forward/YYYY-MM-DD_YYYY-MM-DD/
    │   ├── XXXXXX.parquet   # 原始行情数据（OHLCV）
    │   └── processed/       # 预热后的特征数据（含指标）
    ├── hot_symbols/         # 热门股票列表
    └── CSI300_components.csv # CSI300成分股列表
```

---

## 1. 数据层 (get_data.py)

### GetData 类职责
- **多源数据获取**：支持 TickFlow、AKShare 等API
- **数据清洗**：统一字段、格式、时间序列校验
- **批量下载**：支持并发、断点续传、去重

### 核心方法

#### 数据初始化
```python
python get_data.py
#需要修改warmup中的路径
python warmup.py
```

#### 回测
```python
python lowpe_backtest.py
```

### 常见错误处理
- 缺失数据自动通过扩展日期窗口补齐（见 strategy.py 中 read_data 方法）
- 停牌/异常价格通过 price scale validation 过滤
- 重复数据自动去重

---

## 2. 因子层 (alpha.py)

### AlphaFactor 类设计

#### 初始化与参数
```python
from alpha import AlphaFactor, TechnicalParams

# 使用默认参数
alpha = AlphaFactor()

# 自定义参数
params = TechnicalParams(
    ma_periods={'short': 5, 'medium': 10, 'long': 20, 'super_long': 250},
    rsi_period=14,
    bollinger_period=20,
    bollinger_std=2,
    volume_ma_period=20,
    atr_period=14
)
alpha = AlphaFactor(params=params)
```

#### 技术指标计算（静态方法）

**移动均线**
```python
# EMA（指数加权移动均线）
ema5 = AlphaFactor.calculate_ema(df['close'], period=5)
```

**动量指标**
```python
# RSI（相对强弱指标）
rsi = AlphaFactor.calculate_rsi(df['close'], period=14)

# MACD（移动平均线收敛散度）
macd, signal, hist = AlphaFactor.calculate_macd(df['close'])

# 收益率
ret_1d = AlphaFactor.calculate_return(df['close'], period=1)
ret_10d = AlphaFactor.calculate_return(df['close'], period=10)
```

**波动率与风险**
```python
# ATR（真实波幅）
atr = AlphaFactor.calculate_atr(df, period=14)

# Bollinger Band（布林线）
bb_upper, bb_middle, bb_lower = AlphaFactor.calculate_bollinger_bands(
    df['close'], period=20, std_dev=2
)
```

**成交量**
```python
# OBV（能量潮指标）
obv = AlphaFactor.calculate_obv(df['close'], df['volume'])

# Stochastic Oscillator（随机指标）
percentK, percentD = AlphaFactor.calculate_stochastic(df['close'], window=14)
```

**估值代理**
```python
# 基于价格的估值代理（PE代理）
# pe_ttm = close / rolling_median(close, 252天)
pe_ttm = AlphaFactor.calculate_pe_ttm(df, close_col='close', window=252)

# 估值所处历史分位数（0~1）
pe_position = AlphaFactor.calculate_pe_position(df['pe_ttm'], window=252)
# pe_position=0.3 表示历史30分位（相对便宜）
# pe_position=0.8 表示历史80分位（相对昂贵）
```

#### 批量计算所有指标
```python
# 一次性为 DataFrame 计算所有启用的技术指标
df_with_indicators = alpha.calculate_indicators(df)
# 输出包含：MA5, MA10, MA20, MA250, Return_1d, pe_ttm, pe_position 等列
```

### 因子扩展规范
- **新增因子必须实现为静态方法**，便于并行计算和测试
- **方法签名**：`@staticmethod def calculate_xxx(df/series) -> pd.Series`
- **健壮性**：所有计算应处理 NaN、inf 等异常值
- **文档**：简要说明因子含义、计算逻辑、适用场景

**新增因子示例**
```python
@staticmethod
def calculate_custom_factor(df: pd.DataFrame, window: int = 20) -> pd.Series:
    """
    自定义因子计算示例
    
    Parameters
    ----------
    df : pd.DataFrame
        包含 'close', 'volume' 等列的行情数据
    window : int
        计算窗口大小
        
    Returns
    -------
    pd.Series
        计算结果，与 df 索引对齐
    """
    factor = (df['close'] * df['volume']).rolling(window).mean()
    return factor.fillna(0)

# 在 calculate_indicators 中调用
def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
    df['custom_factor'] = self.calculate_custom_factor(df, window=20)
    return df
```

---

## 3. 策略层 (strategy.py)

### 策略基类 (Strategy)

#### 核心设计
- **生命周期管理**：before_open → on_open → on_close → after_close
- **状态追踪**：assets / unavailable_assets（T+1规则）/ buy_dates / buy_prices
- **订单管理**：自动记录所有买卖操作
- **选股框架**：evaluate_symbol + get_recommend 并行处理

#### 初始化（基类）
```python
from strategy import Strategy

strategy = Strategy(
    data_path='data/CN_Index/daily/forward/2016-01-01_2026-01-01/processed',
    date='2024-06-01',
    assets=pd.DataFrame({'symbol': ['600000'], 'position': [100]}),  # 当前持仓
    cash=50000.0,                                                      # 可用现金
    commission_pct=0.001,                                              # 0.1% 手续费
    commission_fixed=5.0,                                              # 最低5元
    stock_pool=['000001', '000002', ...],                              # 选股范围
    history_recommend=pd.DataFrame(columns=['date', 'symbol']),       # 历史推荐
    lot_size=100,                                                      # 1手=100股
)
```

#### 生命周期钩子（子类覆写）
```python
class MyStrategy(Strategy):
    
    def before_open(self):
        """开盘前准备（如数据加载）"""
        pass
    
    def on_open(self):
        """开盘时执行（如止盈、清仓、买入）"""
        # 示例：按照昨日推荐开仓
        self.buy_at_open()
    
    def on_close(self):
        """收盘前执行（如调整仓位）"""
        # 示例：止盈
        self.sell_open_to_high()
    
    def after_close(self, max_workers: int = 5):
        """收盘后执行（如选股）"""
        # 示例：并行扫描选出明日可买股票
        self.get_recommend(top_n=10, max_workers=max_workers)
```

#### 核心交易方法

**单只股票操作**
```python
# 买入 XXX 金额的股票（以收盘价）
real_value, position = strategy.buy(
    symbol='600000',
    trade_value=10000.0,     # 计划买入金额
    type='close'              # 使用收盘价（也支持'open'等）
)
# 返回：(实际扣款金额含佣金, 成交股数)

# 卖出 XXX 数量的股票
real_money = strategy.sell(
    symbol='600000',
    position=100,             # 卖出100股
    type='close'              # 使用收盘价
)
# 返回：实际到账金额（扣除佣金）
```

**批量操作**
```python
# 按均等权重买入多只股票
symbols = ['600000', '000001', '000002']
strategy.buy_symbols(
    symbols=symbols,
    price_type='open'   # 开盘价买入
)

# 卖出指定股票或全部持仓
strategy.sell_symbols(
    symbols=['600000'],     # None 时卖出全部
    price_type='close'
)

# 便捷方法
strategy.buy_at_open()      # 按今天推荐以开盘价买入
strategy.buy_at_close()     # 按今天推荐以收盘价买入
strategy.sell_at_close()    # 全部清仓（收盘价）
strategy.sell_at_open()     # 低开时全部清仓（开盘价）
strategy.sell_open_to_high()  # 从开盘到最高价区间卖出（止盈）
```

#### 持仓与风控

**止盈：利用自动追踪的买入价**
```python
def on_close(self):
    # buy_dates / buy_prices 由基类自动维护
    for symbol, buy_price in self.buy_prices.items():
        current_price = self.get_price(symbol, type='high')
        
        # 若最高价超过买入价 25%，则以最高价卖出
        if current_price >= buy_price * 1.25:
            self.sell(symbol, self.assets[self.assets['symbol']==symbol]['position'].values[0], type='high')
```

**强制清仓（持仓天数限制）**
```python
def on_open(self):
    current_date = pd.to_datetime(self.date)
    
    for symbol, buy_date in self.buy_dates.items():
        days_held = (current_date - buy_date).days
        
        # 若持仓超过90天，则以开盘价清仓
        if days_held > 90:
            pos = self.assets[self.assets['symbol']==symbol]['position'].values[0]
            self.sell(symbol, pos, type='open')
```

**最大持仓限制**
```python
def on_open(self):
    if len(self.assets) > self.max_stock_num:
        # 逻辑：卖出最差表现股票，保持数量约束
        pass
```

#### 选股框架

**实现 evaluate_symbol（必须覆写）**
```python
def evaluate_symbol(self, symbol: str) -> Optional[Dict]:
    """
    对单只股票评分。返回字典必须包含：
      symbol: 股票代码
      passed: bool, 是否通过筛选
      score: float, 可选，排序用分数（高者优先）
    """
    try:
        df = self.read_data(symbol, trade_days=252)
        if df.empty:
            return {'symbol': symbol, 'passed': False}
        
        # 示例：低PE策略
        close = df['close'].iloc[-1]
        median_close_252 = df['close'].median()
        percentile = close / median_close_252
        
        # 收盘价 <= 252日收盘价的 30 分位数则通过
        passed = percentile <= 0.3
        
        return {
            'symbol': symbol,
            'passed': passed,
            'score': -percentile  # 越低越优先（负数保证排序顺序）
        }
    except Exception:
        return {'symbol': symbol, 'passed': False}
```

**并行选股**
```python
def after_close(self, max_workers: int = 5):
    """并行扫描 stock_pool，选出明日可买的股票"""
    self.get_recommend(
        top_n=10,              # 选出前10只
        max_workers=max_workers # 5个并行线程
    )
    # 结果存储在 self.recommend_symbols 和 self.history_recommend
```

#### 完整策略示例（低PE策略）

见 **strategy.py 中 LowPEstrategy** 类实现。关键特性：
- 每日选出 PE 最低的 top_n 只股票
- 开盘以开盘价均等买入
- 持仓中若日内最高价触及止盈，则以最高价卖出
- 持仓超过 max_hold_days 天则以开盘价强制清仓
- 最多持有 max_stock_num 只股票

---

## 4. 回测层 (backtest.py / lowpe_backtest.py)

### 基础回测框架 (BackTest)

#### 使用场景
- 通用回测框架，支持任意 Strategy 子类
- 自动遍历交易日、累积结果、保存文件

#### 基本用法
```python
from backtest import BackTest
from strategy import MyStrategy

backtest = BackTest(
    initial_cash=1000000.0,
    start_date='2024-01-01',
    end_date='2024-12-31',
    data_path='data/CN_Index/daily/forward/2016-01-01_2026-01-01/processed',
    stock_pool=['000001', '000002', ...],
    commission_pct=0.001,   # 0.1%
    commission_fixed=5.0    # 最低5元
)

# 执行回测
results = backtest.run_strategy(output_path='data/backtest_results')
```

### 专用回测类 (LowPEBackTest)

#### 特性
- 继承自 BackTest
- 针对 LowPEstrategy 增加策略特定参数
- 支持持仓追踪跨交易日传递
- 支持 checkpoint（中间保存）

#### 完整示例
```python
from lowpe_backtest import LowPEBackTest
from pathlib import Path
import numpy as np

# 1. 准备数据
data_path = Path('data/CN_Index/daily/forward/2016-01-01_2026-01-01/processed')
symbols = [p.stem for p in data_path.glob('*.parquet')]

# 2. 随机抽取股票池
rng = np.random.default_rng(seed=42)
stock_pool = rng.choice(symbols, size=min(10000, len(symbols)), replace=False)

# 3. 初始化回测
backtest = LowPEBackTest(
    initial_cash=1_000_000,
    start_date='2020-01-01',
    end_date='2025-12-31',
    data_path=str(data_path),
    stock_pool=stock_pool.tolist(),
    commission_pct=0.001,
    # 策略参数
    lookback_days=252,       # 回看252天
    percentile=0.3,          # 选PE分位 <= 30% 的股票
    max_hold_days=90,        # 最多持仓90天
    max_stock_num=10,        # 最多持有10只
    max_weight=1/10,         # 单股权重不超过10%
    stop_profit=0.25,        # 止盈阈值：+25%
    random_select=True,      # 同一分位数内随机选择
    random_seed=42,
    max_median_open_price=1000.0,  # 过滤异常价格
)

# 4. 执行回测（带 checkpoint）
backtest.run_strategy(
    output_path='data/backtest_results',
    checkpoint=True,         # 启用中间保存
    save_every_n=20          # 每20个交易日保存一次
)

# 5. 最终保存
backtest.save_results(output_path='data/backtest_results', checkpoint=False)
```

#### 回测结果文件

回测完成后会生成以下文件（保存在 `data/backtest_results/YYMMDD-HH_MM/` 目录）：

| 文件名 | 说明 |
|--------|------|
| `backtest_results.csv` | 每日总资产值记录（date, total_value） |
| `order_history.csv` | 全部订单流水（date, symbol, signal, position, price, trade_value） |
| `backtest_params.csv` | 回测参数记录（初始资金、手续费、策略参数等） |

#### 结果分析示例
```python
import pandas as pd
import numpy as np

# 读取回测结果
results = pd.read_csv('data/backtest_results/YYMMDD-HH_MM/backtest_results.csv')

# 计算收益率
results['daily_return'] = results['total_value'].pct_change()
cumulative_return = (results['total_value'].iloc[-1] / results['total_value'].iloc[0]) - 1

# 计算夏普比
annual_volatility = results['daily_return'].std() * np.sqrt(252)
sharpe = (results['daily_return'].mean() * 252) / annual_volatility

# 最大回撤
cummax = results['total_value'].expanding().max()
drawdown = (results['total_value'] - cummax) / cummax
max_drawdown = drawdown.min()

print(f"总收益: {cumulative_return:.2%}")
print(f"夏普比: {sharpe:.2f}")
print(f"最大回撤: {max_drawdown:.2%}")
```

---

## 5. 数据预热 (warmup.py)

### 作用
- 在回测前批量计算所有技术指标、Alpha因子
- 存储到 `processed/` 目录，回测时直接读取（加速）

### 使用方法
```python
from warmup import warm_up_data

# 为指定日期范围的所有股票预热
warm_up_data(
    data_path='data/CN_Index/daily/forward/2016-01-01_2026-01-01',
    is_jump=True    # True=跳过已预热的，False=重新预热全部
)

# 预热完成后会在以下目录生成：
# data/CN_Index/daily/forward/2016-01-01_2026-01-01/processed/XXXXXX.parquet
```

### 输出数据结构
```
processed 目录中的 parquet 文件包含原始列 + 计算的指标列：

原始列：date, open, close, high, low, volume
新增列：
  - MA5, MA10, MA20, MA250        # 移动均线
  - Return_1d                      # 1日收益率
  - pe_ttm                         # PE估值代理
  - pe_position                    # PE估值分位
  （其他指标按 alpha.calculate_indicators 启用情况添加）
```

---

## 6. 开发规范

### 命名规范
```python
# 类名：大驼峰
class LowPEstrategy:
    pass

# 函数/方法：小写+下划线
def calculate_pe_ttm(df):
    pass

# 常量：全大写+下划线
MAX_POSITION_SIZE = 10
DEFAULT_LOOKBACK_WINDOW = 252

# 参数：小写+下划线
initial_cash = 1000000
max_hold_days = 90
```

### 文档字符串
```python
def evaluate_symbol(self, symbol: str) -> Optional[Dict]:
    """
    对单只股票评分。
    
    Parameters
    ----------
    symbol : str
        股票代码（如 '600000'）
    
    Returns
    -------
    Dict or None
        评分结果字典，包含 'symbol', 'passed', 可选 'score'
        若评估失败返回 None 或 passed=False
    
    Examples
    --------
    >>> result = strategy.evaluate_symbol('600000')
    >>> result
    {'symbol': '600000', 'passed': True, 'score': 0.85}
    """
    pass
```

### 错误处理
```python
import logging

try:
    df = self.read_data(symbol, trade_days=252)
    result = do_calculation(df)
except FileNotFoundError as e:
    self.logger.error(f"数据文件缺失: {symbol}")
    return None
except Exception as e:
    self.logger.error(f"计算出错: {str(e)}")
    raise
```

### 兼容性要求
- 新增策略必须继承 Strategy
- run_today() 返回格式固定：`((total_value, cash, assets, order_history), history_recommend)`
- 新增指标必须实现为 AlphaFactor 的静态方法
- 所有新参数通过 __init__ 传入，不修改方法签名

---

## 7. 常见用法速查

### 快速启动回测
```bash
cd /Users/mlwang/Documents/Quants/csi300PEstrategy
conda activate adata
python lowpe_backtest.py
```

### 预热数据
```python
from warmup import warm_up_data
warm_up_data('data/CN_Index/daily/forward/2016-01-01_2026-01-01', is_jump=True)
```

### 下载新数据
```python
from get_data import GetData
gd = GetData(start_date='2025-01-01', end_date='2026-01-01', data_dir='data/CN_Index')
gd.batch_download_tickflow(['000001.SZ', '000002.SZ', ...])
```

### 测试新策略
```python
from strategy import Strategy
from backtest import BackTest

class MyNewStrategy(Strategy):
    def evaluate_symbol(self, symbol):
        # 实现选股逻辑
        return {'symbol': symbol, 'passed': True, 'score': 0.5}
    
    def on_open(self):
        self.buy_at_open()
    
    def on_close(self):
        self.sell_at_close()
    
    def after_close(self, max_workers=5):
        self.get_recommend(top_n=10, max_workers=max_workers)

# 运行回测
backtest = BackTest(
    initial_cash=100000,
    start_date='2024-01-01',
    end_date='2024-12-31',
    data_path='data/CN_Index/daily/forward/2016-01-01_2026-01-01/processed',
    stock_pool=['000001', '000002', ...],
)
backtest.run_strategy(output_path='data/backtest_results')
backtest.save_results()
```

---

## 8. 故障排查

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 数据缺失/不足60行 | 股票停牌或数据不足 | read_data 自动扩展窗口；LowPEBackTest 通过 price scale 过滤 |
| 回测速度慢 | 未预热数据或并发数过低 | 运行 warm_up_data；增加 max_workers 参数 |
| 选股为空 | 筛选条件过严或股票池过小 | 检查 evaluate_symbol 逻辑；扩大 percentile 阈值 |
| 手续费计算不对 | commission_pct/commission_fixed 参数错误 | 确认参数单位：pct 为小数，fixed 为元 |
| T+1 规则违反 | 当日买入当日卖出 | Strategy 基类自动管理 unavailable_assets；on_open 中无法卖出当天买入的股票 |

---

## 9. 后续开发方向

- [ ] 支持期货、期权等衍生品
- [ ] 增加日内交易策略（分钟级数据）
- [ ] 实现多策略组合引擎
- [ ] 参数优化工具（WFO / Walk Forward）
- [ ] 实时交易接口（与 CTP 对接）
- [ ] 风险管理增强（VaR、压力测试）

---

**本 SKILL 文件是完整的框架文档与开发指南，覆盖从数据获取、因子计算、策略开发到回测的全链路。**
**后续更新请保持此格式，并及时补充新增功能和最佳实践。**