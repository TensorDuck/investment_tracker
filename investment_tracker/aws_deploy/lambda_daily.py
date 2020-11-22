"""Lambda handler for checking the current stock price (and change from previous day)"""
import datetime
import logging
import os
import time
from decimal import Decimal
from typing import Callable, List

import boto3
import requests
from boto3.dynamodb.conditions import Key

from investment_tracker.common import AV_API_KEY

TICKER_LIST = ["VOO", "SBUX", "INTC", "AMD", "SPOT", "WORK", "SQ"]
RECIPIENTS = [os.getenv("EMAIL_A"), os.getenv("EMAIL_B")]
RECIPIENTS_ID = [os.getenv("USER_ID_A"), os.getenv("USER_ID_B")]
TABLE_NAME = os.getenv("TABLE_NAME")

logger = logging.getLogger(__name__)
logger.setLevel("INFO")


def clean_fields(results: dict, fields: List[str], clean_fn: Callable) -> dict:
    """Clean each field in the result dict with a clean_fn, i.e. convert to float

    Args:
        results: Result json from a request made to the AlphaVantage API
        fields: List of fields to parse from the result
        clean_fn: function to clean/parse the values

    Returns:
        dict of snake-case keys and cleaned results
    """
    data = {}
    for k in fields:
        data[snakeify(k[4:])] = clean_fn(results[k])

    return data


def snakeify(val: str):
    """Format val as a snake-case"""
    return val.strip().replace(" ", "_").replace("-", "_").lower()


def load_current_price(symbol: str):
    """Use an API call to get the percent change of a stock price

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
        f"&symbol={symbol}&apikey={AV_API_KEY}"
    )
    result.raise_for_status()
    result_dict = result.json()["Global Quote"]

    # clean the results into a snake-case dict keys
    needed_fields = {
        "string_fields": ["01. symbol"],
        "float_fields": [
            "02. open",
            "03. high",
            "04. low",
            "05. price",
            "08. previous close",
            "09. change",
        ],
        "integer_fields": ["06. volume"],
        "date_fields": ["07. latest trading day"],
        "percent_fields": ["10. change percent"],
    }
    return {
        **clean_fields(result_dict, needed_fields["float_fields"], lambda s: float(s)),
        **clean_fields(result_dict, needed_fields["integer_fields"], lambda s: int(s)),
        **clean_fields(
            result_dict, needed_fields["percent_fields"], lambda s: float(s[:-1])
        ),
    }


def _get_current_info(symbol: str) -> str:
    results = load_current_price(symbol)

    change_percent = results["change_percent"]
    change_percent_str = f"{change_percent}%"
    if change_percent > 0:
        change_percent_str = f"+{change_percent}%"
    current_price_str = results["price"]

    time.sleep(12)
    return f"{change_percent_str} - {current_price_str}"


def _construct_user_portfolio(
    portfolio_table: str, user_id: str, gcp_investment_tracker_api: str
) -> str:
    # DynamoDB boto3 resource for the expected table
    table = boto3.resource("dynamodb").Table(portfolio_table)
    # get all stocks for user_0:
    response = table.query(KeyConditionExpression=Key("pkey").eq(user_id))
    stock_lots = response["Items"]
    # begin constructing message
    portfolio = {}
    for item in stock_lots:
        ticker = item["ticker"]
        price = float(item["price"])
        n_shares = float(item["n_shares"])
        n_sold_shares = float(
            item["sold"]["short_term_shares"] + item["sold"]["long_term_shares"]
        )
        reinvest = item.get("reinvest", False)  # must be boolean
        logger.info(f"{ticker}")

        if n_shares - n_sold_shares > 0:  # still has shares left
            # Calculate price/share adjustment
            shares_diff = n_shares - n_sold_shares
            starting_shares = n_shares
            # overwrite with new adjusted prices/shares
            price = price * (shares_diff / starting_shares)
            n_shares = shares_diff
            if ticker not in portfolio:
                portfolio[ticker] = {"start": 0.0, "end": 0.0, "baseline_end": 0.0}
            portfolio[ticker]["start"] += price

            # calcualte return of security
            response_security = requests.post(
                f"{gcp_investment_tracker_api}/returns/",
                json={
                    "ticker": ticker,
                    "start_value": price,
                    "start_shares": n_shares,
                    "start_date": item["first_dividend_date"],
                    "reinvest": reinvest,
                },
            )
            response_security.raise_for_status()
            portfolio[ticker]["end"] += float(response_security.json()["value"])

            # calculate return if a baseline was bought instead
            response_baseline = requests.post(
                f"{gcp_investment_tracker_api}/returns-baseline/",
                json={"start_value": price, "start_date": item["purchase_date"],},
            )
            response_baseline.raise_for_status()
            portfolio[ticker]["baseline_end"] += float(
                response_baseline.json()["value"]
            )

    # Construct the stock message in string format
    message = f"Stock | Current Value |  Net Returns  | Percent Returns | S&P500 Beat\n"
    for security, returns in portfolio.items():
        start_value = returns["start"]
        current_value = returns["end"]
        baseline_value = returns["baseline_end"]
        net_returns = current_value - start_value
        percent_returns = (net_returns / start_value) * 100
        baseline_percent_returns = ((baseline_value - start_value) / start_value) * 100
        baseline_beat = percent_returns - baseline_percent_returns

        message += f"{security:<5} | {current_value:13.2f} | {net_returns:13.2f} | {percent_returns:15.3f} | {baseline_beat:15.3f}\n"

    return message


def lambda_daily(event, context):
    ses = boto3.client("ses")
    subject = f"Stock Update - {datetime.date.today()}"

    # Check GCP API for current investments
    gcp_investment_tracker_api = os.getenv("GCP_investment_tracker_API", None)
    if gcp_investment_tracker_api:
        for recipient, recipient_id in zip(RECIPIENTS, RECIPIENTS_ID):
            message_a = _construct_user_portfolio(
                TABLE_NAME, recipient_id, gcp_investment_tracker_api
            )
            ses.send_email(
                Source="jchen978+AWSses@gmail.com",
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Body": {"Text": {"Charset": "UTF-8", "Data": message_a}},
                    "Subject": {"Data": subject},
                },
            )
    return {"statusCode": 200, "body": {"message": "Success!"}}
