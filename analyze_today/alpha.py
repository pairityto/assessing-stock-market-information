import logging
from typing import Dict, Optional, Tuple
import pandas as pd
from datetime import datetime
import numpy as np



# -------------------------------
# **技术指标配置**
# -------------------------------

from dataclasses import dataclass
@dataclass
class TechnicalParams:
    """技术指标参数配置"""
    ma_periods: Dict[str, int]
    rsi_period: int
    bollinger_period: int
    bollinger_std: int
    volume_ma_period: int
    atr_period: int

    @classmethod
    def default(cls) -> 'TechnicalParams':
        """返回默认的技术指标参数"""
        return cls(
            ma_periods={'short': 5, 'medium': 10, 'long': 20, 'super_long': 250},
            rsi_period=14,
            bollinger_period=20,
            bollinger_std=2,
            volume_ma_period=20,
            atr_period=14
        )


class AlphaFactor:
    """
    优先使用无状态函数/静态方法（例如 Alpha.rsi(df) 或模块级函数）。
    简单、线程/进程安全、易并行化、易测试。
    """
    def __init__(self, params: Optional[TechnicalParams] = None) -> None:
        """
        初始化股票分析引擎
        """
        self._setup_logging()
        self.params = params or TechnicalParams.default()

    def _setup_logging(self) -> None:
        """配置日志记录"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)

    @staticmethod
    def calculate_ema(series: pd.Series, period: int) -> pd.Series:
        """计算 EMA"""
        return series.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_return(series: pd.Series, period: int = 1) -> pd.Series:
        """计算收益率"""
        return series.pct_change(periods=period).fillna(0)

    @staticmethod
    def calculate_rsi(series: pd.Series, period: int) -> pd.Series:
        """
        计算 RSI（指数加权移动平均法）
        """
        delta = series.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
        avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-10)
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calculate_macd(series: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """计算 MACD、信号线和直方图"""
        exp1 = series.ewm(span=12, adjust=False).mean()
        exp2 = series.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        return macd, signal, macd - signal

    @staticmethod
    def calculate_bollinger_bands(series: pd.Series, period: int, std_dev: int) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """计算 Bollinger 通道"""
        middle = series.rolling(window=period, min_periods=period).mean()
        std = series.rolling(window=period, min_periods=period).std()
        upper = middle + std * std_dev
        lower = middle - std * std_dev
        return upper, middle, lower

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int) -> pd.Series:
        """计算 ATR"""
        high = df['high']
        low = df['low']
        prev_close = df['close'].shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(window=period, min_periods=period).mean()

    @staticmethod
    def calculate_obv(series_close: pd.Series, series_volume: pd.Series) -> pd.Series:
        """计算 OBV（能量潮指标）"""
        diff = series_close.diff().fillna(0)
        obv = np.where(diff > 0, series_volume, np.where(diff < 0, -series_volume, 0))
        return pd.Series(obv, index=series_close.index).cumsum()

    @staticmethod
    def calculate_stochastic(series_close: pd.Series, window: int = 14) -> Tuple[pd.Series, pd.Series]:
        """
        计算随机指标（Stochastic Oscillator）
           %K = (close - lowest_low) / (highest_high - lowest_low)*100
           %D 为 %K 的3日简单移动平均
        """
        lowest = series_close.rolling(window=window, min_periods=window).min()
        highest = series_close.rolling(window=window, min_periods=window).max()
        percentK = (series_close - lowest) / (highest - lowest + 1e-10) * 100
        percentD = percentK.rolling(window=3, min_periods=3).mean()
        return percentK, percentD
    
    @staticmethod
    def calculate_pe_ttm(df: pd.DataFrame, close_col: str = "close", window: int = 252) -> pd.Series:
        """
        仅基于OHLCV估算估值水平代理（非真实财务PE）：
        pe_ttm_proxy = close / rolling_median(close, window)
        """
        if close_col not in df.columns:
            raise ValueError(f"缺少价格列: {close_col}")

        close = pd.to_numeric(df[close_col], errors="coerce")
        rolling_median = close.rolling(window=window, min_periods=window).median()
        pe_proxy = close / (rolling_median + 1e-10)
        pe_proxy = pe_proxy.replace([np.inf, -np.inf], np.nan)
        return pe_proxy

    @staticmethod
    def calculate_pe_position(pe_series: pd.Series, window: int = 252) -> pd.Series:
        """
        计算估值代理所处历史位置（0~1 分位）。
        数值越低表示相对历史更便宜，越高表示相对历史更贵。
        """
        def _percentile_of_last(values: np.ndarray) -> float:
            valid = values[~np.isnan(values)]
            if valid.size == 0:
                return np.nan
            last = valid[-1]
            return float(np.sum(valid <= last) / valid.size)

        series = pd.to_numeric(pe_series, errors="coerce")
        return series.rolling(window=window, min_periods=window).apply(_percentile_of_last, raw=True)

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算所有技术指标，并增加 OBV 和随机指标"""
        try:
            # 移动均线
            for key, period in self.params.ma_periods.items():
                df[f'MA{period}'] = self.calculate_ema(df['close'], period)
            df['Return_1d'] = self.calculate_return(df['close'], period=1)
            # df['RSI'] = self.calculate_rsi(df['close'], self.params.rsi_period)
            # df['MACD'], df['Signal'], df['MACD_hist'] = self.calculate_macd(df['close'])
            # df['BB_upper'], df['BB_middle'], df['BB_lower'] = self.calculate_bollinger_bands(
            #     df['close'], self.params.bollinger_period, self.params.bollinger_std)
            # df['Volume_MA'] = df['volume'].rolling(window=self.params.volume_ma_period,
            #                                        min_periods=self.params.volume_ma_period).mean()
            # df['Volume_Ratio'] = df['volume'] / (df['Volume_MA'] + 1e-10)
            # df['ATR'] = self.calculate_atr(df=df, period=self.params.atr_period)
            # df['Volatility'] = df['ATR'] / df['close'] * 100
            # df['ROC'] = df['close'].pct_change(periods=10) * 100

            # 估值代理（仅基于OHLCV）及其历史位置
            df['pe_ttm'] = self.calculate_pe_ttm(df, close_col='close', window=252)
            df['pe_position'] = self.calculate_pe_position(df['pe_ttm'], window=252)

            # # 增加 OBV 指标
            # df['OBV'] = self.calculate_obv(df['close'], df['volume'])
            # df['OBV_MA10'] = df['OBV'].rolling(window=10, min_periods=10).mean()

            # # 增加随机指标 Stochastic
            # df['%K'], df['%D'] = self.calculate_stochastic(df['close'], window=14)

            return df

        except Exception as e:
            self.logger.error(f"指标计算出错：{str(e)}")
            raise
