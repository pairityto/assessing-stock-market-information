import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import akshare as ak
import pandas as pd
from datetime import datetime, timedelta
import time
import akshare as ak
from tickflow import TickFlow
import contextlib
import io
import os

tf = TickFlow(api_key="tk_80cbdb5edac24017b3481dccbc41c428")

#todo
# 1. 增加self.universe属性
# 2. 根据标的池修改保存路径


class GetData:

    def __init__(self, symbol_list=None, 
                 start_date: Optional[str] = None, 
                 end_date: Optional[str] = None, 
                 data_dir='./data'):
        self.symbol_list = symbol_list
        self.start_date = start_date
        self.end_date = end_date
        if not Path(data_dir).exists():
            logging.info(f"Data directory {data_dir} does not exist. Creating it.")
            Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.data_path = Path(data_dir)
        self._setup_logging()

        if not start_date:
            self.start_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
            print(f"Start date not provided. Defaulting to one year ago: {self.start_date}")
        if not end_date:
            self.end_date = datetime.now().strftime('%Y-%m-%d')
            print(f"End date not provided. Defaulting to today: {self.end_date}")

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            tf = TickFlow.free()


        
    def _setup_logging(self) -> None:
        """配置日志记录"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)


    def _get_all_symbols(self, universe: str = '"CN_Equity_A"') -> List[str]:
        """
        获取所有上交所和深交所的股票列表，形如 '600725.SH'。
        如果要获取ETF可以用"CN_ETF".
        获取全部标的池 tf.universes.list()
        这个func的问题是没法得知是否为ST
        """
        try:
            universe = tf.universe.get(universe)

            symbols = pd.Series(universe['symbols'], name="stock_code")
            symbols.to_csv(self.data_path / f"all_symbols_{universe['name']}.csv", index=False)

            return symbols.to_list() #还需要返回标的池名称

        except Exception as e:
            self.logger.error(f"获取股票列表失败：{str(e)}")
            raise


    def _find_exchange(self, stock_code: str) -> str:
        code = str(stock_code).strip().upper().replace("SZ", "").replace("SH", "").replace(".", "").zfill(6)
        parquet_path = self.data_path / "all_stocks.parquet"

        if not parquet_path.exists():
            raise FileNotFoundError(f"未找到股票列表文件: {parquet_path}")

        all_stocks = pd.read_parquet(parquet_path, engine="pyarrow")
        all_stocks["stock_code"] = all_stocks["stock_code"].astype(str).str.zfill(6)
        matched = all_stocks.loc[all_stocks["stock_code"] == code]

        if matched.empty:
            raise ValueError(f"在 {parquet_path} 中未找到股票代码: {code}")

        exchange = str(matched.iloc[0]["exchange"]).upper()
        if exchange not in {"SZ", "SH"}:
            raise ValueError(f"无效交易所标识: {exchange}")

        return exchange
    

    def get_ohlcv_tickflow(self, stock_code, period="1d", adjust="forward", is_Save=False) -> pd.DataFrame:
        """
        获取单只股票的历史数据，包含日期、开盘、收盘、最高、最低、成交量等信息
        :param period: 周期: "daily", "weekly", "monthly"
        :param adjust: choice of {"forward": "前复权", "backward": "后复权", "none": "不复权",
        "forward_additive"	加减法前复权, "backward_additive"	加减法后复权}
        """
        if stock_code is None:
            self.logger.error("股票代码列表为空，无法获取数据")
            raise ValueError("股票代码列表不能为空")
        
        # if not stock_code.endswith(('.SZ', '.SH')):
        #     code = str(stock_code).strip().upper().replace("SZ", "").replace("SH", "").replace(".", "").zfill(6)
        #     exchange = self._find_exchange(stock_code)
        #     stock_code = f"{code}.{exchange}"
            # print(f"已将输入代码转换为标准格式: {stock_code}")

        if is_Save:
            out_dir = self.data_path / "daily"/ adjust/ f"{self.start_date}_{self.end_date}"
            out_dir.mkdir(parents=True, exist_ok=True)
            file_path = out_dir / f"{str(stock_code).strip().split('.')[0]}.parquet"
            if file_path.exists():
                self.logger.info(f"{stock_code} 的数据已存在，跳过下载.")
                return 0



        
        try:

            # 将日期转换为毫秒时间戳
            y, m, d = map(int, self.start_date.split("-"))
            start = int(datetime(y,m,d).timestamp() * 1000)
            y, m, d = map(int, self.end_date.split("-"))
            end = int(datetime(y,m,d).timestamp() * 1000)

            df = tf.klines.get(
                stock_code,
                period=period,
                start_time=start,
                end_time=end,
                count=10000,
                as_dataframe=True,
                adjust=adjust,
            )

            df = df.rename(columns={
                "trade_date": "date",
            })
            df = df[['date', 'open', 'close', 'high', 'low', 'volume']]


            required_columns = {'date', 'open', 'close', 'high', 'low', 'volume'}
            missing_columns = required_columns - set(df.columns)
            if missing_columns:
                raise ValueError(f"缺失必须字段: {missing_columns}")
            
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            numeric_columns = ['open', 'close', 'high', 'low', 'volume']
            df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors='coerce')
            df_cleaned = df.dropna(subset=['date'] + numeric_columns).sort_values('date')

            if len(df_cleaned) < 60:
                print(ValueError(f"数据不足（仅 {len(df_cleaned)} 行），无法计算至少60日均线"))
            
            if is_Save:
                df_cleaned.to_parquet(file_path, index=False, engine="pyarrow", compression="snappy")
                print(f"{stock_code} 的数据已保存到 {file_path}")

            return 1
        
        except Exception as e:
            self.logger.error(f"获取股票数据失败：{str(e)}")
            raise

    def clean_tickflow_data(self, df: pd.DataFrame):
        """
        清洗和验证从 TickFlow 获取的原始数据，确保包含必要的字段并进行数据验证。并保存在目录中
        """
        try:

            df = df.rename(columns={
                "trade_date": "date",
            })
            df = df[['date', 'open', 'close', 'high', 'low', 'volume']]


            required_columns = {'date', 'open', 'close', 'high', 'low', 'volume'}
            missing_columns = required_columns - set(df.columns)
            if missing_columns:
                raise ValueError(f"缺失必须字段: {missing_columns}")
            
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            numeric_columns = ['open', 'close', 'high', 'low', 'volume']
            df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors='coerce')
            df_cleaned = df.dropna(subset=['date'] + numeric_columns).sort_values('date')

            return df_cleaned
    
        except Exception as e:
            self.logger.error(f"获取股票数据失败：{str(e)}")
            raise


    
    def batch_download_tickflow(self, symbols: List[str] = None, period="1d", adjust="forward"):
        """
        批量下载股票数据，保存为 parquet 文件。
        因为数据都是存放在指定日期的文件夹，因此直接跳过已存在文件。
        """
        if isinstance(symbols, str):
            symbols = [symbols]
        elif symbols is None:
            symbols = self._get_all_symbols() 

        out_dir = self.data_path / "daily"/ adjust/ f"{self.start_date}_{self.end_date}"
        out_dir.mkdir(parents=True, exist_ok=True)

        # 将日期转换为毫秒时间戳
        y, m, d = map(int, self.start_date.split("-"))
        start = int(datetime(y,m,d).timestamp() * 1000)
        y, m, d = map(int, self.end_date.split("-"))
        end = int(datetime(y,m,d).timestamp() * 1000)

        # 获取已有的symbols，去重后排除
        existing_symbols = set()
        if out_dir.exists():
            existing_files = list(out_dir.glob("*.parquet"))
            existing_symbols = {f.stem for f in existing_files}

        # 仅对比股票代码的数字部分，但保留原始symbols格式用于下载
        symbols_to_download = [
            s for s in symbols
            if s.split(".")[0] not in existing_symbols
        ]

        if not symbols_to_download:
            print("所有symbols已下载，无需重复下载")
            return

        #尽管TickFlow支持批量下载，但它一定要所有数据请求完毕后才返回dfs
        #这里分批下载，避免中途出问题
        batch_size = 300
        for small_batch in [symbols_to_download[i:i+batch_size] for i in range(0, len(symbols_to_download), batch_size)]:
            print(f"正在下载 {len(small_batch)} 只股票的数据...")


            dfs = tf.klines.batch(
                            symbols=small_batch,
                            period=period,
                            start_time=start,
                            end_time=end,
                            adjust=adjust,
                            count=2000, #可以直接获取指定数量交易日的数据，无需自己计算日期范围
                            batch_size=30,
                            as_dataframe=True,
                            show_progress=False,  # 显示进度条
                            max_workers=5        # 控制并发数，避免过载
                        )

            # 遍历所有股票
            for symbol, df in dfs.items():

                if df.empty:
                    print(f"{symbol}: No valid data after cleaning, skipping.")
                    continue
                elif 'ST' in df.iloc[0]['name']:
                    # print(f"{symbol}: ST股票，跳过.")
                    continue
                else:
                    df_cleaned = self.clean_tickflow_data(df)

                    file_path = out_dir / f"{str(symbol).strip().split('.')[0]}.parquet"
                    df_cleaned.to_parquet(file_path, index=False, engine="pyarrow", compression="snappy")


def save_hot_symbols(save_path: str = 'data/hot_symbols'):
    """保存热门股票列表到文本文件,文件名为每天日期"""
    try:

        from adata import sentiment


        save_path = Path(save_path)
        save_path.mkdir(parents=True, exist_ok=True)
        today = datetime.now().strftime('%Y-%m-%d')
        save_path = save_path / f"hot_{today}.csv"

        #同花顺
        hot_ths = sentiment.hot.hot_rank_100_ths()
        #东方财富
        hot_east = sentiment.hot.pop_rank_100_east()

        hot_symbols = set(hot_ths['stock_code']).union(set(hot_east['stock_code']))
        hot_symbols = list(hot_symbols)

        hot_symbols_df = pd.DataFrame({'date': [today] * len(hot_symbols), 'symbol': hot_symbols})
        hot_symbols_df.to_csv(save_path, index=False)
        print(f"热门股票列表已保存到 {save_path}")
    except Exception as e:
        print(f"保存热门股票列表失败: {str(e)}")


def save_csi300_data(output_path: str):
    """
    获取CSI300成分股数据，清洗并保存为TickFlow格式。
    :param output_path: 保存清洗后数据的文件路径。
    """
    try:
        # 获取CSI300成分股数据
        df = ak.index_stock_cons_csindex(symbol="000300")

        # 提取成分券代码和交易所列
        df['交易所代码'] = df['交易所'].map({
            '深圳证券交易所': 'SZ',
            '上海证券交易所': 'SH'
        })

        # 拼接成TickFlow格式的代码
        df['TickFlow代码'] = df['成分券代码'].str.zfill(6) + '.' + df['交易所代码']

        # 保存到指定路径
        df.to_csv(output_path, index=False, header=True)
        print(f"清洗后的CSI300成分股数据已保存到 {output_path}")
    except Exception as e:
        print(f"获取和保存CSI300成分股数据失败: {str(e)}")



if __name__ == "__main__":

    from warmup import warm_up_data

    # start = "2016-01-01"
    # end = "2026-01-01"
    # getdata = GetData(start_date=start, end_date=end)
    # getdata.batch_download_tickflow()
    # warm_up_data(f'data/daily/forward/{start}_{end}', is_jump=True)
    # try:
    #     save_hot_symbols()
    # except Exception as e:
    #     print(f"保存热门股票列表失败: {str(e)}")


    # get CN_Index 成分股列表
    # universe = tf.universes.get("CN_Index")
    # symbols = universe['symbols']
    # print(len(symbols))
    start = "2015-01-01"
    end = "2026-05-01"
    getdata = GetData(start_date=start, end_date=end, data_dir='data/CN_Index')

    if not Path('data/CSI300_components.csv').exists():
        save_csi300_data('data/CSI300_components.csv')
    else:
        print("CSI300成分股数据已存在，跳过下载.")
        df = pd.read_csv('data/CSI300_components.csv')
        symbols = df['TickFlow代码'].tolist()
        print(f"已加载 {len(symbols)} 只股票的CSI300成分股数据.")
    
    index = 1
    sleep_time = 60  # 每次请求后等待0.1秒，避免过快请求导致问题
    for symbol in symbols:
        print(f"正在下载 {symbol} 的数据...")
        exist = getdata.get_ohlcv_tickflow(symbol, period="1d", adjust="forward", is_Save=True)
        if exist == 0:
            print(f"{symbol} 的数据已存在，跳过下载.")
            continue
        index += 1
        if index % 10 == 0:
            print(f"已下载 {index} 只股票的数据，等待 {sleep_time} 秒...")
            time.sleep(sleep_time)