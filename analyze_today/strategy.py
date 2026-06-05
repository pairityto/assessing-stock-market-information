import os
import logging
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


class Strategy:
    """
    通用量化策略基类。

    包含完整的订单管理、仓位管理、数据读取、选股框架和日内生命周期钩子。
    子类只需覆写 evaluate_symbol（选股评分）和 on_open / on_close（交易时机），
    不需要重复任何资金、订单或持仓管理代码。

    持仓状态由 buy_dates / buy_prices 自动跟踪（在 buy/sell 调用时维护），
    子类可直接使用这两个字典实现止盈、强制清仓等风控逻辑。
    """

    def __init__(
        self,
        data_path: str,
        date: Optional[str] = None,
        assets: Optional[pd.DataFrame] = None,
        cash: float = 0,
        commission_pct: float = 0.001,
        commission_fixed: float = 5.0,
        stock_pool: Optional[Sequence[str]] = None,
        history_recommend: Optional[pd.DataFrame] = None,
        lot_size: int = 100,
        buy_dates: Optional[Dict[str, pd.Timestamp]] = None,
        buy_prices: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Parameters
        ----------
        data_path : str
            行情数据目录，每只股票为一个 parquet 文件（以股票代码命名）。
        date : str, optional
            当前交易日，格式 'YYYY-MM-DD'，默认今日。
        assets : pd.DataFrame, optional
            当前可用持仓，字段 ['symbol', 'position']。
        cash : float
            当前可用现金。
        commission_pct : float
            按交易金额比例收取的佣金费率，如 0.001 表示 0.1%。
        commission_fixed : float
            最低佣金（元），如 5.0。
        stock_pool : Sequence[str], optional
            选股范围，股票代码列表。
        history_recommend : pd.DataFrame, optional
            历史推荐记录（跨回测日传递），字段 ['date', 'symbol']。
        lot_size : int
            A 股最小交易单位，默认 100 股（1 手）。
        """
        self.date: str = date or pd.Timestamp.now().strftime("%Y-%m-%d")
        self.data_path: str = str(data_path)
        self.cash: float = float(cash)
        self.commission_pct: float = float(commission_pct)
        self.commission_fixed: float = float(commission_fixed)
        self.lot_size: int = int(lot_size)

        # 可用持仓（T+1 规则下可操作的部分）
        self.assets: pd.DataFrame = (
            assets.copy() if assets is not None
            else pd.DataFrame(columns=["symbol", "position"])
        )

        # T+1：当日买入的股票当天不可卖，次日结算时并入 assets
        self.unavailable_assets: pd.DataFrame = pd.DataFrame(columns=["symbol", "position"])

        # 订单流水记录
        self.order_history: pd.DataFrame = pd.DataFrame(
            columns=["date", "symbol", "signal", "position", "price_type", "price", "trade_value"]
        )

        # 选股范围与历史推荐（用于跨日传递推荐记录）
        self.stock_pool: List[str] = [str(s) for s in stock_pool] if stock_pool is not None else []
        self.history_recommend: pd.DataFrame = (
            history_recommend.copy() if history_recommend is not None
            else pd.DataFrame(columns=["date", "symbol"])
        )

        # 当日推荐股票（由 get_recommend 在 after_close 时填充，供次日 on_open 使用）
        self.recommend_symbols: List[str] = []
        # 从历史记录中恢复上一次的推荐
        if not self.history_recommend.empty and "symbol" in self.history_recommend.columns:
            last = self.history_recommend.iloc[-1]["symbol"]
            if isinstance(last, list):
                self.recommend_symbols = last

        # 持仓跟踪：记录每只股票的首次买入日期和加权平均买入价，用于止盈/强制清仓
        self.buy_dates: Dict[str, pd.Timestamp] = buy_dates if buy_dates is not None else {}  # symbol -> 买入日期
        self.buy_prices: Dict[str, float] = buy_prices if buy_prices is not None else {}         # symbol -> 加权平均买入价

        self._setup_logging()

        # Alpha 因子计算器（用于 warm_up；不影响策略主逻辑）
        self.alpha = None
        try:
            from alpha import AlphaFactor
            self.alpha = AlphaFactor()
        except Exception:
            pass  # alpha 不可用时 warm_up 会给出明确报错

    # ------------------------------------------------------------------
    # 日志
    # ------------------------------------------------------------------

    def _setup_logging(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # 数据读取
    # ------------------------------------------------------------------

    def read_data(self, symbol: str, trade_days: int = 10) -> pd.DataFrame:
        """
        读取最近 trade_days 个交易日的行情数据。
        自动扩展日期窗口以覆盖节假日，保证返回足够的交易日数据。
        """
        target_date = pd.to_datetime(self.date)
        path = os.path.join(self.data_path, f"{symbol}.parquet")

        # 分层扩大窗口，兼容长假/停牌，尽量拿到“截至当日最近可用”的 trade_days 条数据。
        multipliers = (1.5, 5.0, 20.0, 80.0)
        df = pd.DataFrame()
        for m in multipliers:
            lookback_days = max(int(trade_days * m), trade_days + 1)
            start_date = target_date - pd.Timedelta(days=lookback_days)
            df_try = pq.read_table(
                path, filters=[("date", ">=", start_date), ("date", "<=", target_date)]
            ).to_pandas()
            if len(df_try) >= trade_days:
                df = df_try
                break
            if len(df_try) > len(df):
                df = df_try

        # 兜底：若仍不足，直接取 <= target_date 的全部可用数据再截尾。
        # 该分支仅在极端稀疏/长期停牌时触发，避免 get_price 因空表抛错导致组合估值断崖。
        if len(df) < trade_days:
            df = pq.read_table(path, filters=[("date", "<=", target_date)]).to_pandas()

        return df.tail(trade_days).reset_index(drop=True)

    def get_price(self, symbol: str, type: str = "close") -> float:
        """获取指定股票当日某价格字段（open / high / low / close）。"""
        df = self.read_data(symbol=symbol, trade_days=1)
        if df.empty:
            raise ValueError(f"No market data for {symbol} at {self.date}")
        return float(df[type].values[0])

    def _is_low_open(self, symbol: str, ratio: float = -0.05) -> bool:
        """
        判断股票是否低开。
        ratio 为负数，表示开盘相对前收盘的跌幅阈值（如 -0.05 表示跌超 5% 视为低开）。
        低开时通常不在开盘卖出，以避免在已经低位追杀。
        """
        df = self.read_data(symbol=symbol, trade_days=2)
        if len(df) < 2:
            self.logger.warning("Not enough data to check low open for %s.", symbol)
            return False
        yesterday_close = df.iloc[-2]["close"]
        today_open = df.iloc[-1]["open"]
        return bool(today_open < yesterday_close * (1 + ratio))

    # ------------------------------------------------------------------
    # 佣金与仓位计算
    # ------------------------------------------------------------------

    def calculate_commission(self, trade_value: float) -> float:
        """计算佣金：取比例佣金与固定最低佣金的较大值。"""
        return max(float(trade_value) * self.commission_pct, self.commission_fixed)

    def calculate_position(self, trade_value: float, price: float) -> Tuple[float, float]:
        """
        根据可用资金和价格计算实际可买数量（向下对齐到 lot_size 整数倍）。
        返回 (实际扣款金额含佣金, 实际买入股数)；资金不足时返回 (0.0, 0.0)。
        """
        commission = self.calculate_commission(trade_value)
        position = (trade_value - commission) // price
        position = (position // self.lot_size) * self.lot_size  # A 股最小交易单位对齐
        if position <= 0:
            self.logger.error(
                "资金不足，无法买入。trade_value=%.2f, price=%.2f, commission=%.2f",
                trade_value, price, commission,
            )
            return 0.0, 0.0
        real_value = position * price + commission
        return float(real_value), float(position)

    def calculate_sell_value(self, symbol: str, position: float, price: float) -> float:
        """计算卖出后实际到账金额（扣除佣金）。"""
        if symbol not in self.assets["symbol"].values:
            self.logger.error("Symbol %s not found in assets.", symbol)
            return 0.0
        if position <= 0:
            self.logger.error("Position must be positive.")
            return 0.0
        current_pos = self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0]
        if position > current_pos:
            self.logger.error("Position to sell exceeds available position.")
            return 0.0
        trade_value = float(position) * float(price)
        return trade_value - self.calculate_commission(trade_value)

    # ------------------------------------------------------------------
    # 核心交易操作
    # ------------------------------------------------------------------

    def order(
        self,
        symbol: str,
        signal: str,
        trade_value: float,
        position: float,
        price_type: str,
        price: float,
    ) -> pd.DataFrame:
        """将一笔订单追加到 order_history 流水表。"""
        if signal not in ["buy", "sell"]:
            raise ValueError("Signal must be 'buy' or 'sell'.")
        if trade_value <= 0:
            raise ValueError("Trade value must be positive.")
        self.order_history = pd.concat(
            [self.order_history, pd.DataFrame([{
                "date": self.date,
                "symbol": str(symbol),
                "signal": signal,
                "position": float(position),
                "price_type": price_type,
                "price": float(price),
                "trade_value": float(trade_value),
            }])],
            ignore_index=True,
        )
        return self.order_history

    def buy(self, symbol: str, trade_value: float, type: str = "close") -> Tuple[float, float]:
        """
        买入指定股票。

        - T+1：买入股票放入 unavailable_assets，次日结算后才可卖。
        - 自动更新 buy_dates（首次买入日期）和 buy_prices（加权平均买入价），
          供子类止盈/强制清仓逻辑直接使用。
        返回 (实际成交金额, 成交股数)；失败时返回 (0.0, 0.0)。
        """
        price = self.get_price(symbol, type=type)
        real_value, position = self.calculate_position(trade_value, price)
        if position <= 0 or real_value > self.cash:
            self.logger.error(
                "Buy failed: required=%.2f, available=%.2f for %s", real_value, self.cash, symbol
            )
            return 0.0, 0.0

        self.cash -= real_value
        self.order(symbol, "buy", trade_value=real_value, position=position, price_type=type, price=price)

        # T+1：放入不可用仓
        self.unavailable_assets = pd.concat(
            [self.unavailable_assets, pd.DataFrame([{"symbol": str(symbol), "position": position}])],
            ignore_index=True,
        )

        # 维护买入跟踪：若已持有则更新加权平均买入价，否则新建记录
        if symbol in self.buy_prices:
            # 查询当前合计持仓（可用 + 不可用）作为加权基数
            existing = 0.0
            if symbol in self.assets["symbol"].values:
                existing += float(self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0])
            if symbol in self.unavailable_assets["symbol"].values:
                # 包含刚才追加的，需减去本次新增
                ua_pos = float(self.unavailable_assets.loc[
                    self.unavailable_assets["symbol"] == symbol, "position"
                ].sum()) - position
                existing += ua_pos
            total = existing + position
            if total > 0:
                self.buy_prices[symbol] = (existing * self.buy_prices[symbol] + position * price) / total
        else:
            self.buy_dates[symbol] = pd.to_datetime(self.date)
            self.buy_prices[symbol] = float(price)
            self.logger.debug("Set buy_dates[%s] = %s, buy_prices[%s] = %.2f", symbol, self.date, symbol, price)

        return real_value, position

    def sell(self, symbol: str, position: float, type: str = "close") -> float:
        """
        卖出指定股票的指定数量。

        - 仅允许卖出 assets 中的可用持仓（T+1，当日买入不可卖）。
        - 完全清仓后自动清理 buy_dates / buy_prices 记录。
        返回实际到账金额；失败时返回 0.0。
        """
        if symbol not in self.assets["symbol"].values:
            self.logger.error("Sell failed: %s not in assets.", symbol)
            return 0.0
        if position <= 0:
            self.logger.error("Sell failed: position must be positive.")
            return 0.0
        current_pos = self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0]
        if position > current_pos:
            self.logger.error(
                "Sell failed: requested=%.0f > available=%.0f for %s.", position, current_pos, symbol
            )
            return 0.0

        price = self.get_price(symbol, type=type)
        real_value = self.calculate_sell_value(symbol, position, price)

        self.cash += real_value
        self.order(symbol, "sell", trade_value=real_value, position=position, price_type=type, price=price)
        self.assets.loc[self.assets["symbol"] == symbol, "position"] -= position

        # 完全清仓时清除持仓跟踪
        remaining = float(self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0])
        if remaining <= 0:
            self.buy_dates.pop(symbol, None)
            self.buy_prices.pop(symbol, None)

        return float(real_value)

    # ------------------------------------------------------------------
    # 选股框架（子类覆写 evaluate_symbol 实现策略特有逻辑）
    # ------------------------------------------------------------------

    def _append_recommend_history(self, symbols: Sequence[str]) -> pd.DataFrame:
        """将当日推荐股票追加到 history_recommend，并更新 recommend_symbols。"""
        self.recommend_symbols = [str(s) for s in symbols]
        self.history_recommend = pd.concat(
            [self.history_recommend, pd.DataFrame({"date": [self.date], "symbol": [self.recommend_symbols]})],
            ignore_index=True,
        )
        return self.history_recommend

    def evaluate_symbol(self, symbol: str) -> Optional[Dict]:
        """
        对单只股票进行评分与过滤。子类覆写此方法实现选股逻辑。

        返回字典格式：
          - symbol (str): 股票代码
          - passed (bool): 是否通过筛选（True 才进入候选池）
          - score (float, 可选): 排序分数，越高越优先
        """
        return {"symbol": str(symbol), "passed": False, "score": 0.0}

    def rank_candidates(self, candidates: List[Dict]) -> List[str]:
        """对通过筛选的候选股按 score 降序排列，返回股票代码列表。"""
        ranked = sorted(
            candidates,
            key=lambda x: (x.get("score", 0.0), str(x.get("symbol", ""))),
            reverse=True,
        )
        return [str(x["symbol"]) for x in ranked]

    def get_recommend(self, top_n: Optional[int] = None, max_workers: int = 5) -> pd.DataFrame:
        """
        并行扫描 stock_pool，调用 evaluate_symbol 筛选候选股，
        按 score 排序后取前 top_n 只，更新 recommend_symbols 和 history_recommend。
        结果在次日 on_open 时通过 self.recommend_symbols 使用。
        """
        if not self.stock_pool:
            self.logger.info("Stock pool is empty, no recommendation today.")
            return self._append_recommend_history([])

        candidates: List[Dict] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self.evaluate_symbol, sym) for sym in self.stock_pool]
            for future in as_completed(futures):
                result = future.result()
                if result and bool(result.get("passed", False)):
                    candidates.append(result)

        symbols = self.rank_candidates(candidates)
        if top_n is not None and top_n > 0:
            symbols = symbols[:top_n]

        # self.logger.info("Recommended for next open (%d symbols): %s", len(symbols), symbols)
        self.logger.info("Recommended for next open (%d symbols)", len(symbols))
        return self._append_recommend_history(symbols)

    # ------------------------------------------------------------------
    # 批量买卖工具
    # ------------------------------------------------------------------

    def buy_symbols(self, symbols: Sequence[str], price_type: str = "open") -> None:
        """按均等权重买入给定股票列表，资金不足时跳过并记录错误。"""
        if not symbols:
            self.logger.info("No symbols to buy today.")
            return
        trade_value_per_stock = self.cash / len(symbols)
        for symbol in symbols:
            self.buy(str(symbol), trade_value_per_stock, type=price_type)

    def buy_at_open(self) -> None:
        """以开盘价买入当日推荐股票。"""
        self.buy_symbols(self.recommend_symbols, price_type="open")

    def buy_at_close(self) -> None:
        """以收盘价买入当日推荐股票。"""
        self.buy_symbols(self.recommend_symbols, price_type="close")

    def sell_symbols(self, symbols: Optional[Sequence[str]] = None, price_type: str = "close") -> None:
        """卖出指定股票列表的全部可用持仓；symbols=None 时卖出全部持仓。"""
        target = list(symbols) if symbols is not None else self.assets["symbol"].tolist()
        for symbol in target:
            if symbol not in self.assets["symbol"].values:
                continue
            position = self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0]
            if position > 0:
                self.sell(str(symbol), float(position), type=price_type)

    def sell_at_close(self) -> None:
        """以收盘价卖出全部持仓。"""
        self.sell_symbols(price_type="close")

    def sell_at_open(self, ratio: float = -0.04) -> None:
        """
        以开盘价卖出全部持仓。
        若某只股票开盘跌幅超过 ratio（如 -0.04 即超过 4%），则跳过，
        留到收盘再卖，避免在极端低开时追杀。
        """
        for symbol in self.assets["symbol"].tolist():
            position = self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0]
            if position <= 0:
                continue
            if self._is_low_open(symbol, ratio=ratio):
                self.logger.info("%s low-open detected, skip open sell.", symbol)
                continue
            self.sell(symbol, float(position), type="open")

    def sell_between(self, low_type: str = "open", high_type: str = "high") -> None:
        """
        以 [low_type, high_type] 区间内的随机价格卖出全部持仓。
        用于模拟日内区间成交，如 open~high 表示全天可能成交的均价近似。
        """
        for symbol in self.assets["symbol"].tolist():
            position = self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0]
            if position <= 0:
                continue
            low_price = self.get_price(symbol, type=low_type)
            high_price = self.get_price(symbol, type=high_type)
            price = float(np.random.uniform(low_price, high_price))
            real_value = self.calculate_sell_value(symbol, float(position), price)
            self.cash += real_value
            self.order(
                symbol, "sell", trade_value=real_value, position=float(position),
                price_type=f"{low_type}_to_{high_type}", price=price,
            )
            self.assets.loc[self.assets["symbol"] == symbol, "position"] -= position
            # 清除持仓跟踪
            self.buy_dates.pop(symbol, None)
            self.buy_prices.pop(symbol, None)

    def sell_open_to_high(self) -> None:
        """以 open~high 区间随机价格卖出全部持仓。"""
        self.sell_between(low_type="open", high_type="high")

    def sell_low_to_high(self) -> None:
        """以 low~high 区间随机价格卖出全部持仓。"""
        self.sell_between(low_type="low", high_type="high")

    # ------------------------------------------------------------------
    # 生命周期钩子（子类覆写以注入策略特有交易逻辑）
    # ------------------------------------------------------------------

    def before_open(self) -> None:
        """开盘前处理，如额外数据加载、风险预检查等。子类按需覆写。"""
        pass

    def on_open(self) -> None:
        """开盘时处理，如以开盘价买卖。子类按需覆写。"""
        pass

    def on_close(self) -> None:
        """收盘时处理，如以收盘价买卖。子类按需覆写。"""
        pass

    def after_close(self, max_workers: int = 5) -> None:
        """
        收盘后处理，默认执行选股并更新 recommend_symbols 供次日使用。
        子类可覆写以自定义 top_n 或添加其他收盘后逻辑。
        """
        self.get_recommend(max_workers=max_workers)

    # ------------------------------------------------------------------
    # 日终结算与运行入口
    # ------------------------------------------------------------------

    def next_day(self) -> Tuple[float, float, pd.DataFrame, pd.DataFrame]:
        """
        日终结算：
        1. T+1 结算：将当日买入的不可用持仓并入可用持仓。
        2. 按收盘价估算当日总资产。
        3. 返回 (total_value, cash, assets, order_history)。
        """
        # T+1 结算
        self.assets = pd.concat([self.assets, self.unavailable_assets], ignore_index=True)
        if not self.assets.empty:
            self.assets = self.assets.groupby("symbol", as_index=False)["position"].sum()
            self.assets = self.assets[self.assets["position"] > 0].reset_index(drop=True)
        self.unavailable_assets = pd.DataFrame(columns=["symbol", "position"])

        # 计算总资产
        total_value = self.cash
        for symbol in self.assets["symbol"]:
            price = self.get_price(symbol, type="close")
            position = float(self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0])
            total_value += position * price

        self.logger.info(
            "End of day %s: total_value=%.2f, cash=%.2f, positions=%d",
            self.date, total_value, self.cash, len(self.assets),
        )
        return float(total_value), float(self.cash), self.assets, self.order_history

    def run_day(self, max_workers: int = 5) -> Tuple[float, float, pd.DataFrame, pd.DataFrame]:
        """
        按顺序执行完整的一日生命周期：
        before_open -> on_open -> on_close -> after_close -> next_day
        """
        self.before_open()
        self.on_open()
        self.on_close()
        self.after_close(max_workers=max_workers)
        return self.next_day()


# ==============================================================================
# 子类：低分位价格动量策略
# ==============================================================================

class LowPEstrategy(Strategy):
    """
    低分位价格动量策略。

    选股规则：
        当日收盘价 <= 近 lookback_days 日收盘价的 percentile 分位数。

    交易规则：
        - 信号在收盘后确认，T+1 开盘执行买入。
        - 日内最高价 >= 买入均价 * (1 + stop_profit) 时触发止盈，以当日最高价卖出。
        - 持仓天数超过 max_hold_days 时强制清仓，以开盘价卖出。
        - 最多持有 max_stock_num 只股票，单股权重不超过 max_weight。

    buy_dates / buy_prices 由基类 buy() 自动维护，on_open 直接使用即可。
    """

    def __init__(
        self,
        date: str,
        data_path: str,
        assets: Optional[pd.DataFrame] = None,
        cash: float = 0,
        commission_pct: float = 0.001,
        commission_fixed: float = 5.0,
        stock_pool: Optional[Sequence[str]] = None,
        history_recommend: Optional[pd.DataFrame] = None,
        lookback_days: int = 252,
        percentile: float = 0.3,
        max_hold_days: int = 90,
        max_stock_num: int = 5,
        max_weight: float = 0.33,
        stop_profit: float = 0.25,
        random_select: bool = True,
        random_seed: Optional[int] = None,
        liquidate: bool = False,
        buy_dates: Optional[Dict[str, pd.Timestamp]] = None,
        buy_prices: Optional[Dict[str, float]] = None,
    ) -> None:
        super().__init__(
            data_path=data_path,
            date=date,
            assets=assets,
            cash=cash,
            commission_pct=commission_pct,
            commission_fixed=commission_fixed,
            stock_pool=stock_pool,
            history_recommend=history_recommend,
            buy_dates=buy_dates,
            buy_prices=buy_prices,
        )
        self.lookback_days = lookback_days
        self.percentile = percentile
        self.max_hold_days = max_hold_days
        self.max_stock_num = max_stock_num
        self.max_weight = max_weight
        self.stop_profit = stop_profit
        # random_select=True 时从候选池随机抽取，用于对比基准（排除因子有效性）
        self.random_select: bool = random_select
        self._rng = np.random.default_rng(random_seed)
        self.liquidate: bool = liquidate

    def evaluate_symbol(self, symbol: str) -> Optional[Dict]:
        """
        仅筛选：当日收盘价 <= 近 lookback_days 日历史收盘价的 percentile 分位数。
        不再使用横截面 score 排序，仅返回 passed 与 close。
        """

        try:
            df = self.read_data(symbol, trade_days=self.lookback_days + 1)
            if len(df) < self.lookback_days:
                return None
            historical_closes = df["close"].iloc[:-1]
            today_close = float(df["close"].iloc[-1])
            threshold = float(historical_closes.quantile(self.percentile))
            passed = today_close <= threshold
            return {"symbol": symbol, "passed": passed, "close": today_close}
        except Exception as e:
            self.logger.warning("evaluate_symbol failed for %s: %s", symbol, e)
            return None

    def rank_candidates(self, candidates: List[Dict]) -> List[str]:
        """
        在通过分位筛选的股票中，按“收盘价距离中位数”的绝对值从小到大排序。
        返回最接近中位数的 n+3 只股票代码，用于次日开盘买入冗余候选。
        """
        filtered = [x for x in candidates if bool(x.get("passed", False)) and "close" in x]
        if not filtered:
            return []

        median_close = float(np.median([float(x["close"]) for x in filtered]))
        ranked = sorted(
            filtered,
            key=lambda x: (abs(float(x["close"]) - median_close), str(x["symbol"])),
        )
        n = int(getattr(self, "max_stock_num", 5))
        return [str(x["symbol"]) for x in ranked[: n + 3]]

    def get_recommend(self, top_n: Optional[int] = None, max_workers: int = 5) -> pd.DataFrame:
        """
        并行扫描 stock_pool，先做“低于分位线”筛选，再按“接近中位数”排序。
        最终固定推荐 n+3 只（n=max_stock_num），忽略 top_n 以避免与策略约束冲突。
        """
        if not self.stock_pool:
            self.logger.info("Stock pool is empty, no recommendation today.")
            return self._append_recommend_history([])

        candidates: List[Dict] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(self.evaluate_symbol, sym) for sym in self.stock_pool]
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    candidates.append(result)

        symbols = self.rank_candidates(candidates)
        self.logger.info("Recommended for next open (%d symbols)", len(symbols))
        return self._append_recommend_history(symbols)

    def on_open(self) -> None:
        """
        开盘时执行（顺序重要）：
        1. 止盈检查：日内最高价触及目标价格时卖出。
        2. 强制清仓：持仓超过 max_hold_days 天时卖出。
        3. 买入：用剩余空仓槽买入上一日推荐的股票。

        buy_dates / buy_prices 由基类 buy() 维护，此处直接读取使用。
        """
        today = pd.to_datetime(self.date)
        
        # 调试：记录开盘时的持仓状态
        self.logger.info("=" * 60)
        self.logger.info("On Open - Date: %s", self.date)
        self.logger.info("Current assets: %s", self.assets["symbol"].tolist() if not self.assets.empty else [])
        self.logger.info("buy_dates: %s", self.buy_dates)
        self.logger.info("buy_prices: %s", self.buy_prices)
        self.logger.info("max_hold_days: %d", self.max_hold_days)
        self.logger.info("=" * 60)

        # ---- 1. 止盈检查 ----
        for symbol in self.assets["symbol"].tolist():
            if symbol not in self.buy_prices:
                continue
            try:
                high = self.get_price(symbol, type="high")
                if high >= self.buy_prices[symbol] * (1 + self.stop_profit):
                    pos = float(self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0])
                    self.sell(symbol, pos, type="high")
                    self.logger.info(
                        "Stop profit: %s  high=%.2f  entry=%.2f",
                        symbol, high, self.buy_prices[symbol],
                    )
            except Exception as e:
                self.logger.warning("Stop profit check error for %s: %s", symbol, e)

        # ---- 2. 强制清仓 ----
        for symbol in self.assets["symbol"].tolist():
            if symbol not in self.buy_dates:
                self.logger.debug("Symbol %s not in buy_dates (first time holding)", symbol)
                continue
            hold_days = (today - self.buy_dates[symbol]).days
            self.logger.debug("Symbol %s: hold_days=%d, max_hold_days=%d", symbol, hold_days, self.max_hold_days)
            if hold_days >= self.max_hold_days:
                pos = float(self.assets.loc[self.assets["symbol"] == symbol, "position"].values[0])
                self.sell(symbol, pos, type="open")
                self.logger.info("Force close: %s  held=%d days", symbol, hold_days)

        # ---- 3. 买入新股 ----
        # 已持仓数 >= max_stock_num 时直接跳过
        held = set(self.assets.loc[self.assets["position"] > 0, "symbol"].tolist())
        slots = self.max_stock_num - len(held)
        if slots <= 0 or self.cash <= 0:
            return

        # 候选列表：昨日所有通过筛选的推荐股（排除已持仓）
        candidates = [s for s in self.recommend_symbols if s not in held]
        if not candidates:
            return

        # 随机模式：打乱候选顺序，逐个尝试直到买满 slots 支
        # 默认模式：按推荐顺序逐个尝试（推荐列表已按“接近中位数”排序）
        if self.random_select:
            ordered = list(self._rng.permutation(candidates))
        else:
            ordered = candidates

        # 基于总组合价值确定目标仓位（持仓按开盘价估算，体现当日真实可投资规模）
        portfolio_value = self.cash
        for sym in self.assets.loc[self.assets["position"] > 0, "symbol"].tolist():
            try:
                sym_price = self.get_price(sym, type="open")
                sym_pos = float(self.assets.loc[self.assets["symbol"] == sym, "position"].values[0])
                portfolio_value += sym_pos * sym_price
            except Exception:
                pass

        weight = min(self.max_weight, 1.0 / self.max_stock_num)
        max_position_value = portfolio_value * self.max_weight  # 单股硬上限

        bought = 0
        for symbol in ordered:
            if bought >= slots:
                break
            try:
                open_price = self.get_price(symbol, type="open")
            except Exception as e:
                self.logger.warning("Cannot get open price for %s: %s", symbol, e)
                continue
            min_lot_cost = open_price * self.lot_size * (1 + self.commission_pct) + self.commission_fixed
            if min_lot_cost > max_position_value:
                self.logger.info(
                    "Skip %s: 1 lot costs %.2f > max position value %.2f",
                    symbol, min_lot_cost, max_position_value,
                )
                continue

            # 动态预算：每次买入尝试都按“当前可用现金 / 剩余槽位”收缩预算，避免重复固定 trade_value
            remaining_slots = max(slots - bought, 1)
            cash_per_remaining_slot = self.cash / remaining_slots
            base_trade_value = portfolio_value * weight
            target_trade_value = min(base_trade_value, max_position_value, cash_per_remaining_slot)
            trade_value = max(min_lot_cost, target_trade_value)

            # 若连 1 手都买不起，直接跳过
            if min_lot_cost > self.cash:
                self.logger.info(
                    (
                        "Skip %s: min_lot_cost %.2f > available cash %.2f "
                        "(open=%.2f, lot=%d, remaining_slots=%d)"
                    ),
                    symbol,
                    min_lot_cost,
                    self.cash,
                    open_price,
                    self.lot_size,
                    remaining_slots,
                )
                continue

            # 防止浮点误差造成极小超额
            trade_value = min(trade_value, self.cash)
            self.buy(symbol, trade_value, type="open")
            bought += 1

    def on_close(self) -> None:
        """收盘时操作：若 liquidate=True（最后一个回测交易日），强制全仓卖出。"""
        if self.liquidate:
            self.sell_symbols(price_type="close")
            self.logger.info("Liquidated all positions at close on %s", self.date)

    def after_close(self, max_workers: int = 5) -> None:
        """
        收盘后处理：满仓时跳过全池选股以加速回测。

        说明：
        - 当日可用仓在 assets，当日新买入在 unavailable_assets（T+1）。
        - 仅当合并后的持仓股票数小于 max_stock_num 时才有必要重新筛选推荐。
        """
        held_available = (
            set(self.assets.loc[self.assets["position"] > 0, "symbol"].tolist())
            if not self.assets.empty else set()
        )
        held_unavailable = (
            set(self.unavailable_assets.loc[self.unavailable_assets["position"] > 0, "symbol"].tolist())
            if not self.unavailable_assets.empty else set()
        )
        held_total = held_available | held_unavailable

        if len(held_total) >= self.max_stock_num:
            self.logger.info(
                "Skip recommendation scan at close: holdings=%d >= max_stock_num=%d",
                len(held_total), self.max_stock_num,
            )
            return

        self.get_recommend(max_workers=max_workers)

    def run_today(self, max_workers: int = 5) -> Tuple[Tuple[float, float, pd.DataFrame, pd.DataFrame], pd.DataFrame]:
        """
        兼容回测器调用接口，执行完整一日流程。
        返回 ((total_value, cash, assets, order_history), history_recommend)。
        """
        try:
            return self.run_day(max_workers=max_workers), self.history_recommend
        except Exception as e:
            self.logger.error("run_today error: %s", e)
            return (self.cash, self.cash, self.assets, self.order_history), self.history_recommend
