import pandas as pd
import logging
import os


class BackTest():
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
        df = pd.read_parquet("/Users/mlwang/Documents/Quants/workflow_v1/data/daily/forward/2025-04-01_2026-04-01/000001.parquet")
        trading_days = df[(df['date'] >= self.start_date) & (df['date'] <= self.end_date)]['date']
        return trading_days.sort_values().reset_index(drop=True)
    
    def run_strategy(self, strategy_func) -> pd.DataFrame:
        """Run the backtest with the given strategy function."""
        # 1. 获取所有交易日
        trading_days = self.get_trading_days()
        
        # 2. 遍历每个交易日，执行策略函数
        for date in trading_days:
            self.logger.info(f"Running strategy for {date}")

            # 3. 执行策略函数，获取当天的总资产价值、现金余额、持仓情况和订单历史
            total_value, self.cash, self.assets, self.order_history = strategy_func(
                date = date, 
                data_path = self.data_path, 
                assets = self.assets, 
                cash = self.cash,
                commission_pct = self.commission_pct, 
                commission_fixed = self.commission_fixed,
                stock_pool = self.stock_pool
                ).run_today()
            
            self.protofolio_history.loc[len(self.protofolio_history)] = {
                'date': date,
                'total_value': total_value
            }

        # return total_value

    def run_strategy_keep3day(self, strategy_func) -> pd.DataFrame:
        """Run the backtest with the given strategy function."""
        # 1. 获取所有交易日
        trading_days = self.get_trading_days()
        n = 3  # 可按需改为任意间隔天数
        act_days = trading_days.iloc[::n].reset_index(drop=True)
        
        # 2. 遍历每个交易日，执行策略函数
        for date in act_days:

            self.logger.info(f"Running strategy for {date}")

            # 3. 执行策略函数，获取当天的总资产价值、现金余额、持仓情况和订单历史
            total_value, self.cash, self.assets, today_orders = strategy_func(
                date = date, 
                data_path = self.data_path, 
                assets = self.assets, 
                cash = self.cash,
                commission_pct = self.commission_pct, 
                commission_fixed = self.commission_fixed,
                stock_pool = self.stock_pool
                ).run_today()
            
            self.order_history = pd.concat([self.order_history, today_orders], ignore_index=True)
            
            self.protofolio_history.loc[len(self.protofolio_history)] = {
                'date': date,
                'total_value': total_value
            }

        # return total_value

    def save_results(self, output_path: str = 'data/backtest_results') -> None:
        """Save the backtest results to a Parquet file."""
        try:
            today_str = pd.Timestamp.now().strftime('%y%m%d-%H_%M')
            save_path = os.path.join(output_path, today_str)
            os.makedirs(save_path, exist_ok=True)
            self.protofolio_history.to_csv(save_path+"/backtest_results.csv", index=False)
            self.order_history.to_csv(save_path+"/order_history.csv", index=False)
            # 保存回测参数到 CSV
            initial_cash = (
                self.protofolio_history["total_value"].iloc[0]
                if not self.protofolio_history.empty
                else self.cash
            )

            params_df = pd.DataFrame([{
                "start_date": self.start_date,
                "end_date": self.end_date,
                "initial_cash": initial_cash,
                "final_cash": self.cash,
                "commission_pct": self.commission_pct,
                "commission_fixed": self.commission_fixed,
                "data_path": self.data_path,
                "stock_pool_size": len(self.stock_pool) if self.stock_pool is not None else 0,
                "stock_pool": ",".join(map(str, self.stock_pool)) if self.stock_pool is not None else ""
            }])

            params_df.to_csv(save_path + "/backtest_params.csv", index=False, encoding="utf-8-sig")
            self.logger.info(f"Backtest results saved to {save_path}")
        except Exception as e:
            self.logger.error(f"Failed to save backtest results: {str(e)}")
            raise



from strategy import LowPEstrategy
import numpy as np

from pathlib import Path

if __name__ == "__main__":

    data_path = "/Users/mlwang/Documents/Quants/workflow_v1/data/daily/forward/2025-04-01_2026-04-01/processed"
    # assets = pd.DataFrame({'symbol': ['605499', '301082'], 'position': [100, 50]})
    symbols = [p.stem for p in Path(data_path).glob("*.parquet")]
    #先用一支股票进行测试
    stock_pool = np.random.choice(symbols, size=min(5000, len(symbols)), replace=False)
    backtest = BackTest(initial_cash=100000, start_date='2026-02-28', end_date='2026-03-31', data_path=data_path, stock_pool=stock_pool)
    backtest.run_strategy(strategy_func=LowPEstrategy)

    backtest.save_results()