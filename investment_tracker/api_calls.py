"""This module contains methods for loading finance data with api calls"""
import time
from typing import Callable, List

import pandas as pd
import requests

from investment_tracker.common import AV_API_KEY


def snakeify(val: str):
    """Format val as a snake-case"""
    return val.strip().replace(" ", "_").replace("-", "_").lower()


class StockInfo:
    """Parent class for getting stock information from AlphaVantage

    AlphaVantage is an API service that returns real-time and historical
    information for a stock price. This is performed through an HTTP request.

    Requests typically are packaged as strings, so it needs to be able to parse
    the fields into the appropriate format (i.e. floats, ints, dates)

    Field names are typically formatted as "X. field name" i.e. "10. previous
    close".
    """

    # names in fields in snake-case, i.e. "previous_close"
    numeric_fields = []
    date_fields = []
    percent_fields = []

    def __init__(self):
        """Perform the API call and parse the JSON into a data frame"""
        self._stock_info = self.clean_df(pd.DataFrame())

    @property
    def stock_info(self) -> pd.DataFrame:
        return self._stock_info

    def save(self, file_name):
        self.stock_info.to_csv(file_name)

    @staticmethod
    def _convert_field_values(
        df: pd.DataFrame, fields: List[str], convert_fn: Callable
    ) -> pd.DataFrame:
        """Convert each field in the df to correct type with convert_fn
        i.e. convert to float

        Args:
            df: Result json from a request in DataFrame Format
            fields: List of fields to parse from the result
            convert_fn: function to clean/parse the values

        Returns:
            dict of snake-case keys and cleaned results"""
        for k in fields:
            df[k] = convert_fn(df[k])
        return df

    @staticmethod
    def _parse_percent_str_to_float(percent_str: str):
        """Convert a percent str into a float"""
        return float(percent_str.strip().strip("%"))

    def _clean_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """ Clean and convert field values in the data frame

        Args:
            df: The dataframe to clean

        Returns:
            cleaned df
        """
        # Convert column names i.e. '1. last date' to 'last_date'
        df = df.rename(axis=1, mapper=lambda x: snakeify(x.strip().split(". ")[-1]))

        # convert column values
        df = StockInfo._convert_field_values(df, self.numeric_fields, pd.to_numeric)
        df = StockInfo._convert_field_values(df, self.date_fields, pd.to_datetime)
        df = StockInfo._convert_field_values(
            df,
            self.percent_fields,
            lambda s: s.apply(StockInfo._parse_percent_str_to_float),
        )

        return df


class DailyStockInfo(StockInfo):
    numeric_fields = [
        "open",
        "high",
        "low",
        "close",
        "adjusted_close",
        "volume",
        "dividend_amount",
        "split_coefficient",
    ]

    def __init__(self, stock_symbol: str, full: bool = False):
        """ Load the daily stock price for a symbol through Alpha Vantage

        Args:
            stock_symbol: Symbol of security to get
            full: Type of value to get

        Return:
            Daily open/close/high/low price, and volume of security traded
        """
        output = "full" if full else "compact"
        result = requests.get(
            f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED"
            f"&symbol={stock_symbol}&outputsize={output}&apikey={AV_API_KEY}"
        )
        result.raise_for_status()
        time.sleep(12)  # rate-limit access to the AV API
        result = result.json()
        self.ticker = stock_symbol

        try:
            self.metadata = result["Meta Data"]

            df = pd.DataFrame.from_dict(result["Time Series (Daily)"], orient="index")
            df["datetime"] = pd.to_datetime(df.index)
            self._stock_info = self._clean_df(df)
        except:
            raise IOError(result)

    def calculate_value(
        self,
        start_date: str,
        start_shares: int,
        start_amount: float,
        reinvest: bool = False,
    ) -> float:
        """ Calculate the current value of an investment madeon a specific date

        Args:
            start_date: Day investment was made
            start_shares: Number of shares bought on the start_date
            start_amount: Initial investment amount
            reinvest: Whether or not the shares were reinvested into the same stock

        Returns:
            Current value of the investment
        """
        current_shares = start_shares
        current_payout = 0

        # get the daily changes to a stock's value
        daily_changes = self.stock_info[self.stock_info.index >= start_date].sort_index(
            axis=0
        )[["dividend_amount", "split_coefficient", "close"]]

        # incrementally calculate gains
        for _, change in daily_changes.iterrows():
            # increase share count from a stock-split
            current_shares = change["split_coefficient"] * current_shares

            # calculate dividend payout (and if automatic reinvestment happens)
            dividend_payout = change["dividend_amount"] * current_shares
            if reinvest:
                current_shares += dividend_payout / change["close"]
            else:
                current_payout += dividend_payout

        # calculate the final value of the investment
        latest_date = max(daily_changes.index)
        final_value = self.stock_info.loc[latest_date]["close"] * current_shares

        end_total = final_value + current_payout

        return end_total


class CurrentStockInfo(StockInfo):
    numeric_fields = [
        "open",
        "high",
        "low",
        "price",
        "previous_close",
        "change",
        "volume",
    ]
    date_fields = ["latest_trading_day"]
    percent_fields = ["change_percent"]

    def __init__(self, stock_symbol):
        """Use an API call to get the current price of a stock

        Percent change is based off of current price and the previous day's closing price.

        Fields are: symbol, open, high, low, price, volume, latest_trading_day,
        previous_close, change, change_percent

        Args:
            symbol: Ticker symbol for a security.

        Return:
            Percent change (i.e. 0.88 is +.88% change)
        """
        result = requests.get(
            f"https://www.alphavantage.co/query?function=GLOBAL_QUOTE"
            f"&symbol={stock_symbol}&apikey={AV_API_KEY}"
        )
        result.raise_for_status()
        time.sleep(12)  # rate-limit access to the AV API
        result_dict = result.json()["Global Quote"]
        self._stock_info = self._clean_df(pd.DataFrame([result_dict]))
