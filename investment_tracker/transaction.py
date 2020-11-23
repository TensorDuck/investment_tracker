"""Module for interacting with a DynamoDB table of transactions"""
import datetime
import json
from decimal import Decimal

import boto3
import click
from boto3.dynamodb.conditions import Key


def _add_one_calendar_year(dt: datetime.datetime):
    """Create new datetime object one calendar-year ahead"""
    return datetime.datetime(year=dt.year + 1, month=dt.month, day=dt.day)


def _check_dynamo_response_error(response: dict):
    """Check for an error response in the return-dict from Dynamo"""
    http_status = response.get("ResponseMetadata").get("HTTPStatusCode")
    if (http_status < 200) or http_status >= 300:
        raise DynamoError(
            f"Buy operation exited with status code: {http_status}\n, "
            f"contents: {response}"
        )


class DynamoError(Exception):
    pass


class FinancialRecord:
    def __init__(self, security: str, skey: str, n_shares: float, price: float):
        self.security = security
        self.skey = skey
        self.n_shares = n_shares
        self.price = price

    def __str__(self):
        return (
            f"{self.security}.{self.skey} "
            f"- Shares: {self.n_shares} "
            f"- Price: {self.price} "
            f"- Price/Share: {self.price/self.n_shares:.2f} "
        )


class DynamoOperator:
    TODAY = str(datetime.datetime.today().date())

    def __init__(self, user_id: str, table_name="securities"):
        """ Operator for tracking buying/selling of securities in a DynamoDB table

        Args:
            user_id: Unique id identifying a user.
            table_name: Name of DynamoDB table tracking securities.
        """
        self.user_id = user_id
        self.table = boto3.resource("dynamodb").Table(table_name)

    def _get_skey(self, security: str, transaction_date: str):
        """Construct a skey for a particular lot"""
        return f"{security}__{transaction_date}"

    def list_all(self) -> list:
        """Get a list of all purchase lots for the user

        Returns:
            List of all records
        """
        response = self.table.query(KeyConditionExpression=Key("pkey").eq(self.user_id))
        records = []
        for item in response["Items"]:
            records.append(
                FinancialRecord(
                    item.get("ticker"),
                    item.get("skey"),
                    item.get("n_shares"),
                    item.get("price"),
                )
            )

        return records

    def buy(
        self,
        security: str,
        n_shares: float,
        price: float,
        purchase_date: str = TODAY,
        first_dividend_date: str = None,
        reinvest: bool = False,
    ):
        """Construct a purchase record and upload to DynamoDB

        Args:
            security: Ticker symbol of bough security.
            n_shares: Number of shares bought in this lot.
            price: Total price paid.
            purchase_date: Date the purchase was made.
            first_dividend_date: Date when the lot is eligible for dividends.
                I.e. after the next ex-Divdend date. Defaults to purchase_date
        """
        if not first_dividend_date:
            first_dividend_date = purchase_date
        new_skey = self._get_skey(security, purchase_date)
        record = {
            "pkey": self.user_id,
            "skey": new_skey,
            "ticker": security,
            "n_shares": n_shares,
            "price": price,
            "purchase_date": purchase_date,
            "first_dividend_date": first_dividend_date,
            "reinvest": reinvest,
            "sold": {
                "short_term_shares": 0.0,
                "long_term_shares": 0.0,
                "total_price_short": 0.0,
                "total_price_long": 0.0,
                "full_history": [],
            },
        }

        response = self.table.put_item(
            Item=json.loads(json.dumps(record), parse_float=lambda s: Decimal(s)),
            ConditionExpression="attribute_not_exists(skey)",
        )
        _check_dynamo_response_error(response)
        print(response)

    def sell(
        self,
        security: str,
        n_shares: float,
        price: float,
        purchase_date: str,
        sell_date: str = TODAY,
    ):
        """Construct a purchase record and upload to DynamoDB

        Args:
            security: Ticker symbol of sold security.
            n_shares: Number of shares sold in this lot.
            price: Total price received.
            purchase_date: Original date security was bought
            sell_date: Date the selling was made.
        """
        # get the original record
        skey = self._get_skey(security, purchase_date)
        response = self.table.get_item(Key={"pkey": self.user_id, "skey": skey})
        _check_dynamo_response_error(response)
        record = response.get("Item")
        if not record:
            raise DynamoError(f"No record for user={self.user_id}, skey={skey}")

        # construct the new record
        # determine if a short-sale or a long-sale
        sell_datetime = datetime.datetime.strptime(sell_date, "%Y-%m-%d")
        purchase_datetime = datetime.datetime.strptime(purchase_date, "%Y-%m-%d")
        long_tax_cutoff_datetime = _add_one_calendar_year(purchase_datetime)
        # modify the record's sell information
        if sell_datetime > long_tax_cutoff_datetime:
            record["sold"]["long_term_shares"] += Decimal(n_shares)
            record["sold"]["total_price_long"] += Decimal(price)
        else:
            record["sold"]["short_term_shares"] += Decimal(n_shares)
            record["sold"]["total_price_short"] += Decimal(price)
        record["sold"]["full_history"].append(
            {"date": sell_date, "n_shares": Decimal(n_shares), "price": Decimal(price)}
        )
        # confirm the new record makes sense before updating:
        total_sold_shares = (
            record["sold"]["long_term_shares"] + record["sold"]["short_term_shares"]
        )
        if total_sold_shares > record["n_shares"]:
            raise DynamoError(
                "Sold more shares than were bought. "
                f"Sold:{total_sold_shares} out of bought:{record['n_shares']}"
            )
        print(record)
        response = self.table.put_item(Item=record)
        _check_dynamo_response_error


@click.command()
@click.argument("action", required=True)
@click.argument("user", required=True)
@click.option("--security", type=str, help="Ticker symbol for the security.")
@click.option(
    "--n-shares", type=float, help="Amount of shares involved in transaction."
)
@click.option("--price", type=float, help="Total price of the bought/sold security.")
@click.option("--purchase-date", type=str, help="YYYY-MM-DD for the transaction.")
@click.option("--sell-date", type=str, help="YYYY-MM-DD for the transaction")
@click.option(
    "--reinvest/--no-reinvest",
    default=False,
    help="--reinvest means all shares are reinvested. Defaults to --no-reinvest.",
)
@click.option(
    "--first-dividend-date",
    default=None,
    type=str,
    help=(
        "YYYY-MM-DD thats the first eligible for dividends. "
        "Defaults to purchase-date."
    ),
)
def main(
    action,
    user,
    security,
    n_shares,
    price,
    purchase_date,
    sell_date,
    reinvest,
    first_dividend_date,
):
    """Actions for interacting with the """
    operator = DynamoOperator(user)
    if action == "list":
        current_securities = operator.list_all()
        for stock in current_securities:
            print(stock)
    elif action == "buy":
        operator.buy(
            security,
            n_shares,
            price,
            purchase_date,
            first_dividend_date,
            reinvest=reinvest,
        )
    elif action == "sell":
        operator.sell(security, n_shares, price, purchase_date, sell_date)
    else:
        raise IOError("The `action` must be either `list`, `buy`, or `sell`.")


if __name__ == "__main__":
    main()
