import pandas as pd
import logging
import os
from backtest import BackTest
import numpy as np
from pathlib import Path

class copylimitBackTest(BackTest):
    def __init__(self, 
                 initial_cash: float = 100000.0,
                 start_date: str = '2025-04-01',
                 end_date: str = '2026-04-01',
                 data_path: str = f'data/daily/forward/2025-04-01_2026-04-01',
                 stock_pool: list = None,
                 commission_pct: float = 0.001,
                 commission_fixed: float = 5.0):
        self.cash : float = initial_cash
        self.data_path : str = data_path
        self.start_date : str = start_date
        self.end_date : str = end_date
        self.assets : pd.DataFrame = pd.DataFrame(columns=['symbol', 'position'])
        self.unavailable_assets : pd.DataFrame = pd.DataFrame(columns=['symbol', 'position'])
        self.commission_pct : float = commission_pct
        self.commission_fixed : float = commission_fixed
        self.order_history = pd.DataFrame(columns=['date', 'symbol', 'signal', 'position', 'price', 'trade_value'])
        self.protofolio_history = pd.DataFrame(columns=['date', 'total_value'])
        self.stock_pool = stock_pool
        self._setup_logging()


    def _setup_logging(self) -> None:
        """配置日志记录"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)


    def get_trading_days(self) -> pd.Series:
        """Get all trading days between start_date and end_date."""
        # 这里假设数据文件夹中有一个包含所有交易日的文件 trading_days.parquet
        df = pd.read_parquet(Path(self.data_path) / '000001.parquet')
        trading_days = df[(df['date'] >= self.start_date) & (df['date'] <= self.end_date)]['date']
        print(f"Total trading days: {len(trading_days)}")
        return trading_days.sort_values().reset_index(drop=True)
    
    def _record_daily_result(self, date: str, total_value: float, order_history: pd.DataFrame) -> None:
        """Append daily portfolio and order history to internal storage."""
        if order_history is not None and not order_history.empty:
            self.order_history = pd.concat([self.order_history, order_history], ignore_index=True)

        self.protofolio_history = pd.concat([
            self.protofolio_history,
            pd.DataFrame([{'date': date, 'total_value': total_value}])
        ], ignore_index=True)

    def run_strategy(
        self,
        strategy_func,
        output_path: str = 'data/backtest_results',
        checkpoint: bool = False,
        save_every_n: int = 1
    ) -> pd.DataFrame:
        """Run the backtest with the given strategy function."""
        trading_days = self.get_trading_days()
        self.history_recommend = pd.DataFrame(columns=['date', 'symbol'])

        os.makedirs(output_path, exist_ok=True)

        for idx, date in enumerate(trading_days):
            self.logger.info(f"Running strategy for {date}")

            (total_value, self.cash, self.assets, order_history), self.history_recommend = strategy_func(
                date=date,
                data_path=self.data_path,
                assets=self.assets,
                cash=self.cash,
                commission_pct=self.commission_pct,
                commission_fixed=self.commission_fixed,
                stock_pool=self.stock_pool,
                history_recommend=self.history_recommend
            ).run_today(max_workers=10)

            self._record_daily_result(date=date, total_value=total_value, order_history=order_history)

            if checkpoint and ((idx + 1) % save_every_n == 0):
                self.save_results(output_path=output_path, checkpoint=True)

        return self.protofolio_history

    def save_results(
        self,
        output_path: str = 'data/backtest_results',
        checkpoint: bool = True
    ) -> None:
        """Save the backtest results to disk.

        If checkpoint=True, save to a stable checkpoint folder so current progress is available during long runs.
        Otherwise, save a timestamped final result folder.
        """
        try:
            os.makedirs(output_path, exist_ok=True)
            if checkpoint:
                save_path = os.path.join(output_path, 'checkpoint')
            else:
                today_str = pd.Timestamp.now().strftime('%y%m%d-%H_%M')
                save_path = os.path.join(output_path, today_str)

            os.makedirs(save_path, exist_ok=True)
            self.protofolio_history.to_csv(os.path.join(save_path, 'backtest_results.csv'), index=False)
            self.order_history.to_csv(os.path.join(save_path, 'order_history.csv'), index=False)
            self.history_recommend.to_csv(os.path.join(save_path, 'history_recommend.csv'), index=False)

            initial_cash = (
                self.protofolio_history['total_value'].iloc[0]
                if not self.protofolio_history.empty
                else self.cash
            )
            params_df = pd.DataFrame([{
                'start_date': self.start_date,
                'end_date': self.end_date,
                'initial_cash': initial_cash,
                'final_cash': self.cash,
                'commission_pct': self.commission_pct,
                'commission_fixed': self.commission_fixed,
                'data_path': self.data_path,
                'stock_pool_size': len(self.stock_pool) if self.stock_pool is not None else 0,
            }])
            params_df.to_csv(os.path.join(save_path, 'backtest_params.csv'), index=False, encoding='utf-8-sig')
            self.logger.info(f"Backtest results saved to {save_path}")
        except Exception as e:
            self.logger.error(f"Failed to save backtest results: {str(e)}")
            raise


from strategy import LowPEstrategy


if __name__ == "__main__":

    data_path = Path("data/daily/forward/2023-01-01_2026-04-08/processed")
    # assets = pd.DataFrame({'symbol': ['605499', '301082'], 'position': [100, 50]})
    symbols = [p.stem for p in Path(data_path).glob("*.parquet")]
    rng = np.random.default_rng(12345)
    stock_pool = rng.choice(symbols, size=min(10000, len(symbols)), replace=False)
    print("Total available symbols:", len(stock_pool))
    backtest = copylimitBackTest(initial_cash=100000, 
                                 start_date='2024-01-01', 
                                 end_date='2024-08-31', 
                                 data_path=data_path, 
                                 stock_pool=stock_pool,
                                 commission_pct=0.0005,)
    # backtest = copylimitBackTest(initial_cash=114571, start_date='2026-01-01', end_date='2026-02-01', data_path=data_path, stock_pool=stock_pool)
    # backtest.run_strategy(strategy_func=scoreStrategy)
    backtest.run_strategy(checkpoint=True,strategy_func=LowPEstrategy)

    backtest.save_results(checkpoint=False)