import os

from flask import Flask, jsonify, request

from investment_tracker.api_calls import DailyStockInfo

app = Flask(__name__)


@app.route("/returns/", methods=["POST"])
def returns():
    """Calculate the net returns for a security

    Example JSON input:
        {
            "ticker": "SBUX",
            "value": 2400.00,
            "start_shares": 30,
            "start_date": "2020-07-01",
            "reinvest": False,
        }
    """

    body = request.json
    if body:
        # load information from request body
        ticker = body.get("ticker")
        start_date = body.get("start_date")
        start_value = body.get("start_value")
        start_shares = body.get("start_shares")
        reinvest = body.get("reinvest", False)

        # calculate the value, assume no reinvestment
        stock = DailyStockInfo(ticker, full=True)
        value = stock.calculate_value(
            start_date, start_shares, start_value, reinvest=reinvest
        )

        return jsonify(
            {
                "stock": ticker,
                "value": value,
                "percent_change": (value - start_value) / start_value,
            }
        )
    # Default: if body is None, then return a helpful message
    return jsonify(
        {
            "message": (
                "Nothing to see! "
                "Specify ticker, start_date, start_value, and start_shares in a "
                "JSON body to calculate the total returns."
            )
        }
    )


@app.route("/returns-baseline/", methods=["POST"])
def returns_baseline():
    """ Calculate the net returns for the baseline security"""
    baseline_ticker = "FXAIX"
    baseline_stock = DailyStockInfo(baseline_ticker, full=True)
    body = request.json
    if body:
        # load information from request body
        start_date = body.get("start_date")
        start_value = body.get("start_value")

        # Calculate the number of shares that could have hypothetically been bought
        cost = baseline_stock.stock_info.loc[start_date]["close"]
        n_shares = start_value / cost

        # calculate the value, assume no reinvestment
        value = baseline_stock.calculate_value(
            start_date, n_shares, start_value, reinvest=True
        )

        return jsonify(
            {
                "stock": baseline_ticker,
                "value": value,
                "percent_change": (value - start_value) / start_value,
            }
        )
    # Default: if body is None, then return a helpful message
    return jsonify(
        {
            "message": (
                "Nothing to see! "
                "Specify, start_date, and start_value in a "
                "JSON body to calculate the total returns."
            )
        }
    )


@app.route("/", methods=["GET"])
def hello_world():
    # the stock I want to compare and the baseline to compare it to
    ticker = "SBUX"
    baseline = "FXAIX"

    # initialize the classes
    stock = DailyStockInfo(ticker)
    baseline_stock = DailyStockInfo(baseline)

    # the basic purchase info of the stock
    start_date = "2020-07-20"
    start_value = 2442.0
    start_shares = 33

    # calculate the current value of the stock
    value = stock.calculate_value(start_date, start_shares, start_value)

    # calcualte the baseline stock value
    baseline_cost = baseline_stock.stock_info.loc[start_date]["close"]
    baseline_shares = start_value / baseline_cost
    baseline_value = baseline_stock.calculate_value(
        start_date, baseline_shares, start_value, reinvest=True
    )

    return jsonify(
        {
            "stock": "SBUX",
            "starting_value": start_value,
            "start_shares": start_shares,
            "value": value,
            "percent_change": (value - start_value) / start_value,
            "baseline": "VOO",
            "baseline_cost": baseline_cost,
            "baseline_shares": baseline_shares,
            "baseline_value": baseline_value,
            "baseline_percent_change": (baseline_value - start_value) / start_value,
        }
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
