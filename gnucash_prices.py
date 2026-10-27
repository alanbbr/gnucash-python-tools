#!/usr/bin/env python3.12
# -*- coding: utf-8 -*-
"""
Get stock, mutual fund, etc. quotes from Yahoo and others.

Initially from
https://github.com/hjacobs/gnucash-stock-portfolio/blob/master/portfolio.py
with no license specified.

License - CC BY-SA 4.0
"""

import datetime
import gzip
import logging
import os
import re
import sys
import time
import urllib.request
from argparse import ArgumentParser, Namespace
from collections.abc import KeysView
from typing import Any, Optional

import requests  # ty: ignore[unresolved-import]
import yfinance as yf  # ty: ignore[unresolved-import]
from bs4 import BeautifulSoup  # ty: ignore[unresolved-import]
from gnucash import (
    Book,
    GncCommodity,
    GncNumeric,
    GncPrice,
    GnuCashBackendException,
    PriceSource,
    Session,
)

logging.basicConfig(format="%(asctime)-15s %(levelname)s:%(name)s:"
                    "%(funcName)s:%(lineno)d:%(message)s")
logger = logging.getLogger("get_prices")


CURRENCIES = {"$": "USD"}


def get_yahoo_data(
        symbols: dict[str, str], lcd: datetime.date
    ) -> dict[str, tuple[str, float, datetime.date]]:
    """Pull quotes from Yahoo's data."""
    final = {}
    # Filter out all non-Yahoo or all stock symbols
    syms = [kk for kk, vv in symbols.items() if vv in {"y", "Y", "*"}]
    if not syms:
        return final
    # so we can call Yahoo with just what we want from them.
    ticks = yf.Tickers(syms)
    logger.debug(dir(ticks.tickers))
    for kk, vv in ticks.tickers.items():
        try:
            final[kk] = (vv.info["currency"], vv.info["previousClose"], lcd)
        except KeyError:  # noqa: PERF203
            # This will happen if Yahoo does not have data for the given symbol.
            logger.warning("failed to get data for '%s': %r", kk, vv)
    logger.debug(final)
    return final


def get_alpha_vantage_data(
        symbols: dict[str, str], args: Namespace
    ) -> dict[str, tuple[str, float, datetime.date]]:
    """
    Get Alpha Vantage data for symbols marked by a, A or *.

    The API key can from the command line, or from an ALPHAVANTAGE_API_KEY
    environment variable.
    """
    final = {}
    apikey = args.alphavantage
    if not apikey:
        apikey = os.environ.get("ALPHAVANTAGE_API_KEY", None)
    if not apikey:
        return final
    syms = [kk for kk, vv in symbols.items() if vv in {"a", "A", "*"}]
    if not syms:
        return final
    avurl = "https://www.alphavantage.co/query"
    for sym in syms:
        url = avurl + f"?function=GLOBAL_QUOTE&symbol={sym}&apikey={apikey}"
        data = requests.get(url, timeout=10).json()
        logger.debug(data)
        gq = data["Global Quote"]
        parts = gq["07. latest trading day"].split("-")
        ltd = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
        logger.debug(ltd)
        final[sym] = ("USD", float(gq["05. price"]), ltd)
        time.sleep(1)
    logger.debug(final)
    return final


# Source - https://stackoverflow.com/a/61894534
# Posted by aj8907, modified by community. See post 'Timeline' for change history
# Retrieved 2026-10-27, License - CC BY-SA 4.0
def currency_parser(cur_str: str) -> float:
    """Remove any non-numerical characters from the given string, & return as float."""
    # except for "," "." or "-" (e.g. EUR)
    cur_str = re.sub(r"[^-0-9.,]", "", cur_str)
    # Remove any 000s separators (either , or .)
    cur_str = re.sub(r"[.,]", "", cur_str[:-3]) + cur_str[-3:]
    if "," in list(cur_str[-3:]):
        return float(cur_str.replace(",", "."))
    return float(cur_str)


def get_morningstar_data(
        symbols: dict[str, str], lcd: datetime.date
    ) -> dict[str, tuple[str, float, datetime.date]]:
    """Get the morningstar.com page for a given fund, and parse out the close price."""
    final = {}
    syms = [kk for kk, vv in symbols.items() if vv in {"m", "M", "*"}]
    if not syms:
        return final
    for sym in syms:
        url = f"https://www.morningstar.com/funds/xnas/{sym.lower()}/quote"
        logger.debug(url)
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (X11; Linux x86_64; rv:158.0)"
            " Gecko/20100101 Firefox/158.0")
        with urllib.request.urlopen(req) as f:  # noqa S310
            logger.debug(f.headers)
            page = f.read()
            if f.headers.get("Content-Encoding") == "gzip":
                page = gzip.decompress(page)
            logger.debug(page.decode("utf-8", errors="replace"))
        if not page:
            continue
        # parse content
        soup = BeautifulSoup(page, "html.parser")
        spans = soup.find_all("span", {"class": "mdc-data-point--currency"})
        vals = [span.get_text() for span in spans]
        logger.debug(vals)
        spans = soup.find_all("time", {"class": "mdc-date"})
        times = [span["datetime"] for span in spans]
        logger.debug(times)
        # pull & save value
        cur = CURRENCIES.get(vals[0][0], "USD")
        try:
            val = currency_parser(vals[0])
        except Exception:
            logger.exception("Failed to get a valid amount")
            val = 0.0
        try:
            td = datetime.date.fromisoformat(times[1].split('T')[0])
        except Exception:
            logger.exception("Failed to get a valid datetime")
            td = lcd
        final[sym] = (cur.upper(), val, td)
    logger.debug(final)
    return final


def get_stock_closing_prices(
        keys: KeysView[str], args: Namespace, lcd: datetime.date
    ) -> dict[str, tuple[str, float, datetime.date]]:
    """Get the most recent closing price for the given symbol(s)."""
    logger.debug(keys)
    logger.debug(args.symbols)
    symbols = {}
    for vv in args.symbols:
        parts = vv.split(":")
        if parts[0] not in keys:
            continue
        symbols[parts[0]] = parts[1] if len(parts) > 1 else "*"
    logger.debug(symbols)
    final = get_yahoo_data(symbols, lcd)
    data = get_alpha_vantage_data(symbols, args)
    for kk, vv in data.items():
        if kk not in final:
            final[kk] = vv
    data = get_morningstar_data(symbols, lcd)
    for kk, vv in data.items():
        if kk not in final:
            final[kk] = vv
    logger.debug(final)
    return final


# Source - https://stackoverflow.com/a/12053711
# Posted by Martijn Pieters, modified by community.
# See post 'Timeline' for change history
# Retrieved 2026-10-24, License - CC BY-SA 3.0
def prev_weekday(adate: Optional[datetime.date] = None) -> datetime.date:
    """Get the most recent weekday, but not holiday aware."""
    if adate is None:
        adate = datetime.datetime.now()
    offsets = (3, 1, 1, 1, 1, 1, 2)
    return adate - datetime.timedelta(days=offsets[adate.weekday()])


def update_quote(
        com: GncCommodity, quote: tuple[str, float, datetime.date], book: Book
    ) -> None:
    """Add the new data to the GnuCash file."""
    logger.debug(quote)
    if not quote[0] or not isinstance(quote[1], float) or quote[1] < 0.0:
        return
    table = book.get_table()  # ty: ignore[unresolved-attribute]
    p = GncPrice(book)
    p.set_time64(quote[2])  # ty: ignore[unresolved-attribute]
    p.set_commodity(com)  # ty: ignore[unresolved-attribute]
    gnc_currency = table.lookup("ISO4217", quote[0])
    p.set_currency(gnc_currency)  # ty: ignore[unresolved-attribute]
    val = int(quote[1] * 1000)
    logger.debug(val)
    p.set_value(GncNumeric(val, 1000))  # ty: ignore[unresolved-attribute]
    p.set_source(PriceSource.FINANCE_QUOTE)  # ty: ignore[unresolved-attribute]
    p.set_typestr("last")  # ty: ignore[unresolved-attribute]
    book.get_price_db().add_price(p)  # ty: ignore[unresolved-attribute]


def update_symbols(s: Session, args: Namespace) -> None:
    """Verify given symbols are in the GnuCash file, then update the values."""
    symbols = [vv.split(":")[0] for vv in args.symbols]
    lwd = prev_weekday()
    book = s.book  # ty: ignore[unresolved-attribute]
    table = book.get_table()
    coms = {}
    for namespace in table.get_namespaces_list():
        name = namespace.get_name()
        logger.debug(name)
        if name != "CURRENCY":
            for commodity in namespace.get_commodity_list():
                logger.debug(commodity.get_nice_symbol())
                # Make sure we don't try to update something not in the gnucash file.
                if commodity.get_nice_symbol() in symbols:
                    coms[commodity.get_nice_symbol()] = commodity
    logger.debug(coms)
    if not coms:
        return
    data = get_stock_closing_prices(coms.keys(), args, lwd)
    for sym, vals in data.items():
        logger.debug("%s -> %r", sym, vals)
        update_quote(coms[sym], vals, book)


if __name__ == "__main__":
    parser = ArgumentParser(
        description="Get previous close prices from Yahoo for the given symbols"
    )
    parser.add_argument("-D", "--debug", action="store_true")
    parser.add_argument(
        "-N", "--dry-run", action="store_true", help="Do not save quotes"
    )
    parser.add_argument("-a", "--alphavantage", help="Alpha Vantage API key")
    parser.add_argument("gnucash_file", help="path to gnucash file")
    parser.add_argument("symbols", nargs="+", help="1 or more ticker symbols")
    args = parser.parse_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    try:
        s = Session(args.gnucash_file)
    except GnuCashBackendException:
        logger.info("%s is open by another gnucash session.", args.gnucash_file)
        sys.exit(0)
    try:
        update_symbols(s, args)
        if not args.dry_run:
            s.save()  # ty: ignore[unresolved-attribute]
    finally:
        s.end()  # ty: ignore[unresolved-attribute]
