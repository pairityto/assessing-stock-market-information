"""
lowpe_backtest.py
用于回测 LowPEstrategy 的回测类。
"""

import logging
import os
from time import sleep

import numpy as np
import pandas as pd
from pathlib import Path

from backtest import BackTest
from strategy import LowPEstrategy


class LowPEBackTest(BackTest):
    """
    专用于 LowPEstrategy 的回测类。

    相比基类 BackTest，主要增加：
    1. 支持 LowPEstrategy 的策略参数（lookback_days / percentile / max_hold_days 等）。
    2. run_strategy 按 `copylimitBackTest` 约定解包 run_today 的双层返回值：
       ((total_value, cash, assets, order_history), history_recommend)
    3. 每日将订单流水追加到 order_history，将推荐记录传递到下一交易日。
    4. 支持 checkpoint 中间保存。
    """

    def __init__(
        self,
        # ── 基础回测参数 ──────────────────────────────────────────────
        initial_cash: float = 100_000.0,
        start_date: str = "2024-01-01",
        end_date: str = "2024-12-31",
        data_path: str = "data/daily/forward/2023-01-01_2026-04-08/processed",
        stock_pool: list = None,
        commission_pct: float = 0.0005,
        commission_fixed: float = 5.0,
        # ── LowPEstrategy 策略参数 ────────────────────────────────────
        lookback_days: int = 252,
        percentile: float = 0.3,
        max_hold_days: int = 90,
        max_stock_num: int = 5,
        max_weight: float = 0.33,
        stop_profit: float = 0.25,
        max_workers: int = 10,
        random_select: bool = True,
        random_seed: int = None,
        max_median_open_price: float = 1000.0,
    ) -> None:
        super().__init__(
            initial_cash=initial_cash,
            start_date=start_date,
            end_date=end_date,
            data_path=data_path,
            stock_pool=stock_pool,
            commission_pct=commission_pct,
            commission_fixed=commission_fixed,
        )
        # 策略特有参数，保存供 run_strategy 构造 LowPEstrategy 时使用
        self.lookback_days = lookback_days
        self.percentile = percentile
        self.max_hold_days = max_hold_days
        self.max_stock_num = max_stock_num
        self.max_weight = max_weight
        self.stop_profit = stop_profit
        self.max_workers = max_workers
        self.random_select = random_select
        self.random_seed = random_seed
        self.max_median_open_price = float(max_median_open_price)
        # 持久 RNG：跨交易日保持状态，使每天的随机结果不同但整体可复现
        self._rng = np.random.default_rng(random_seed) if random_select else None

        # 过滤非个股代码：先做代码规则过滤，再做价格口径校验。
        # 对于 CN_Index 一类混合数据源，价格校验可进一步剔除指数点位/异常口径数据。
        if self.stock_pool is not None:
            before = len(self.stock_pool)
            by_code = [str(s) for s in self.stock_pool if self._is_tradeable_stock_code(s)]
            code_filtered = before - len(by_code)

            by_price = [s for s in by_code if self._has_reasonable_price_scale(s)]
            price_filtered = len(by_code) - len(by_price)

            self.stock_pool = by_price
            total_filtered = before - len(self.stock_pool)
            print(
                "Filtered stock pool: "
                f"removed_by_code={code_filtered}, removed_by_price={price_filtered}, "
                f"total_removed={total_filtered}, remain={len(self.stock_pool)}"
            )

    @staticmethod
    def _is_tradeable_stock_code(symbol: str) -> bool:
        """按代码规则过滤出 A 股个股代码，剔除指数/ETF/债券等常见非个股代码。"""
        s = str(symbol)
        if len(s) != 6 or not s.isdigit():
            return False

        # A 股常见个股代码前缀（主板/中小板/创业板/科创板/北交所）
        stock_prefixes = ("000", "001", "002", "003", "300", "301", "600", "601", "603", "605", "688", "689")
        if not s.startswith(stock_prefixes):
            return False

        # 常见非个股代码前缀（指数、ETF、LOF、债券基金等）
        non_stock_prefixes = (
            "159", "395", "399", "510", "511", "512", "513", "515", "516", "517",
            "518", "519", "520", "530", "560", "561", "562", "563", "588", "980", "988",
        )
        if s.startswith(non_stock_prefixes):
            return False

        # 常见指数代码白名单中的显式排除
        non_stock_codes = {
            "000001", "000002", "000003", "000016", "000300", "000688", "000852", "000905", "000906"
        }
        if s in non_stock_codes:
            return False

        return True

    def _has_reasonable_price_scale(self, symbol: str) -> bool:
        """价格口径校验：剔除明显指数点位/异常价格口径的 symbol。"""
        try:
            df = pd.read_parquet(Path(self.data_path) / f"{symbol}.parquet", columns=["open"])
            if df.empty:
                return False
            opens = pd.to_numeric(df["open"], errors="coerce").dropna().tail(120)
            if opens.empty:
                return False
            median_open = float(opens.median())
            return 0.01 <= median_open <= self.max_median_open_price
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 获取交易日历
    # ------------------------------------------------------------------

    def get_trading_days(self) -> pd.Series:
        """从数据目录中读取 000001 的行情文件来获取交易日历。"""
        df = pd.read_parquet(Path(self.data_path) / "000001.parquet")
        trading_days = df[
            (df["date"] >= self.start_date) & (df["date"] <= self.end_date)
        ]["date"]
        print(f"Total trading days: {len(trading_days)}")
        return trading_days.sort_values().reset_index(drop=True)

    # ------------------------------------------------------------------
    # 回测主循环
    # ------------------------------------------------------------------

    def run_strategy(
        self,
        output_path: str = "data/backtest_results",
        checkpoint: bool = False,
        save_every_n: int = 20,
    ) -> pd.DataFrame:
        """
        按交易日顺序逐日执行 LowPEstrategy，汇总结果。

        Parameters
        ----------
        output_path : str
            回测结果保存目录。
        checkpoint : bool
            是否启用中间保存（每 save_every_n 天保存一次）。
        save_every_n : int
            checkpoint 保存间隔（交易日数）。

        Returns
        -------
        pd.DataFrame
            每日总资产价值记录，字段 ['date', 'total_value']。
        """
        trading_days = self.get_trading_days()
        history_recommend = pd.DataFrame(columns=["date", "symbol"])
        # 持久化 buy_dates 和 buy_prices，跨交易日传递
        persistent_buy_dates = {}
        persistent_buy_prices = {}

        os.makedirs(output_path, exist_ok=True)

        n_days = len(trading_days)
        for idx, date in enumerate(trading_days):
            self.logger.info("Running LowPEstrategy for %s", date)

            # 每天从持久 RNG 派生一个新 seed，确保各日随机结果不同，整体仍可复现
            day_seed = int(self._rng.integers(0, 2**31)) if self._rng is not None else self.random_seed

            # 最后一个交易日强制清仓（回测结束时归还全部持仓为现金）
            is_last_day = (idx == n_days - 1)

            strategy = LowPEstrategy(
                date=date,
                data_path=self.data_path,
                assets=self.assets,
                cash=self.cash,
                commission_pct=self.commission_pct,
                commission_fixed=self.commission_fixed,
                stock_pool=self.stock_pool,
                history_recommend=history_recommend,
                lookback_days=self.lookback_days,
                percentile=self.percentile,
                max_hold_days=self.max_hold_days,
                max_stock_num=self.max_stock_num,
                max_weight=self.max_weight,
                stop_profit=self.stop_profit,
                random_select=self.random_select,
                random_seed=day_seed,
                liquidate=is_last_day,
                buy_dates=persistent_buy_dates,
                buy_prices=persistent_buy_prices,
            )

            # run_today 返回双层元组：
            # ((total_value, cash, assets, order_history), history_recommend)
            (total_value, self.cash, self.assets, order_history), history_recommend = (
                strategy.run_today(max_workers=self.max_workers)
            )
            
            # 保存当日的持仓追踪信息，传递给下一日
            persistent_buy_dates = strategy.buy_dates.copy()
            persistent_buy_prices = strategy.buy_prices.copy()
            self.logger.info(
                "After day %s: buy_dates has %d entries, buy_prices has %d entries",
                date, len(persistent_buy_dates), len(persistent_buy_prices)
            )

            self._record_daily_result(
                date=date, total_value=total_value, order_history=order_history
            )

            if checkpoint and ((idx + 1) % save_every_n == 0):
                self.save_results(output_path=output_path, checkpoint=True)

        return self.protofolio_history

    # ------------------------------------------------------------------
    # 日结果记录（与 copylimitBackTest 保持一致）
    # ------------------------------------------------------------------

    def _record_daily_result(
        self, date: str, total_value: float, order_history: pd.DataFrame
    ) -> None:
        """追加当日订单流水和总资产到内部存储。"""
        if order_history is not None and not order_history.empty:
            self.order_history = pd.concat(
                [self.order_history, order_history], ignore_index=True
            )
        self.protofolio_history = pd.concat(
            [
                self.protofolio_history,
                pd.DataFrame([{"date": date, "total_value": total_value}]),
            ],
            ignore_index=True,
        )

    # ------------------------------------------------------------------
    # 保存结果
    # ------------------------------------------------------------------

    def save_results(
        self,
        output_path: str = "data/backtest_results",
        checkpoint: bool = False,
    ) -> None:
        """
        将回测结果保存到磁盘。

        Parameters
        ----------
        checkpoint : bool
            True  → 覆盖写入 checkpoint/ 子目录（长时间运行时保留进度）。
            False → 以时间戳命名新子目录保存最终结果。
        """
        try:
            os.makedirs(output_path, exist_ok=True)
            if checkpoint:
                save_path = os.path.join(output_path, "checkpoint")
            else:
                today_str = pd.Timestamp.now().strftime("%y%m%d-%H_%M")
                save_path = os.path.join(output_path, today_str)

            os.makedirs(save_path, exist_ok=True)

            self.protofolio_history.to_csv(
                os.path.join(save_path, "backtest_results.csv"), index=False
            )
            self.order_history.to_csv(
                os.path.join(save_path, "order_history.csv"), index=False
            )

            initial_cash = (
                self.protofolio_history["total_value"].iloc[0]
                if not self.protofolio_history.empty
                else self.cash
            )
            params_df = pd.DataFrame(
                [
                    {
                        "start_date": self.start_date,
                        "end_date": self.end_date,
                        "initial_cash": initial_cash,
                        "final_cash": self.cash,
                        "commission_pct": self.commission_pct,
                        "commission_fixed": self.commission_fixed,
                        "data_path": str(self.data_path),
                        "stock_pool_size": (
                            len(self.stock_pool) if self.stock_pool is not None else 0
                        ),
                        # 策略参数
                        "lookback_days": self.lookback_days,
                        "percentile": self.percentile,
                        "max_hold_days": self.max_hold_days,
                        "max_stock_num": self.max_stock_num,
                        "max_weight": self.max_weight,
                        "stop_profit": self.stop_profit,
                        "random_select": self.random_select,
                        "random_seed": self.random_seed,
                    }
                ]
            )
            params_df.to_csv(
                os.path.join(save_path, "backtest_params.csv"),
                index=False,
                encoding="utf-8-sig",
            )
            self.logger.info("Backtest results saved to %s", save_path)
        except Exception as e:
            self.logger.error("Failed to save backtest results: %s", e)
            raise


# ──────────────────────────────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    data_path = Path("/Users/mlwang/Documents/Quants/csi300PEstrategy/data/CN_Index/daily/forward/2015-01-01_2026-05-01/processed")
    # data_path = Path("/Users/mlwang/Documents/Quants/csi300PEstrategy/data/CN_Index/daily/forward/2016-01-01_2026-01-01/processed")

    symbols = [p.stem for p in data_path.glob("*.parquet")]
    # 不固定 seed：每次运行都抽取不同股票池，适合需要随机性的回测
    rng = np.random.default_rng()
    stock_pool = rng.choice(symbols, size=min(10_000, len(symbols)), replace=False)
    print(f"Total available symbols: {len(stock_pool)}")

    # 进行多次回测以评估随机选股的稳定性
    for i in range(1):

        n = 10 # 每次回测选取 10 支股票，适当增加随机性，同时保持一定的集中度（max_weight=1/10）
        
        backtest = LowPEBackTest(
            initial_cash=1000000,
            start_date="2017-01-01",
            # start_date="2017-01-01",
            end_date="2025-12-31",
            # end_date="2026-01-01",
            data_path=data_path,
            stock_pool=stock_pool,
            commission_pct=0.001,
            # 策略参数（可按需调整）
            lookback_days=252,
            percentile=0.3,
            max_hold_days=90,
            max_stock_num=n,
            max_weight=1/n, #depends on max_stock_num, should be <= 1/max_stock_num
            stop_profit=0.25,
            max_workers=5,
            max_median_open_price=1000.0, # 价格口径过滤阈值，剔除明显指数点位/异常价格口径的 symbol
            random_select=False,
        )

        backtest.run_strategy(checkpoint=True, save_every_n=20)
        backtest.save_results(output_path=f"/Users/mlwang/Documents/Quants/csi300PEstrategy/data/backtest_results/中位数选股-10支-long", checkpoint=False)

        # sleep(30)  # 每次回测间隔 50 秒，避免过快连续运行导致系统资源紧张
