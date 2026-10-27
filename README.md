# gnucash-python-tools

## gnucash_prices.py

For me, gnucash hasn't been getting investment prices for a couple of reasons.
Yahoo, of course, seems to break things just to keep people from using Yahoo,
and the GnuCash code for querying Alpha Vantage seems to have been tested with
only one ticker, or maybe with a paid account. AV doesn't like free accounts
querying more than once per second, or 25 times a day. The latter hasn't been
an issue, but the former effectively breaks the GnuCash provided client.

Taking advantage of the yfinance library, and time.sleep, I have created a
python script that runs outside of GnuCash, when GnuCash does not have the
target file open. That makes for a schedule-able process to update investment
values, for me, once a week. My crontab is:

`4 4 * * 1 /home/alan/.local/bin/gnucash_prices.sh`

Note that I call gnucash_prices.py via a shell script. This enables setting
the PYTHONPATH to the value needed by my build of GnuCash. That is installed
in /usr/local, so the gnucash python libraries are in
`/usr/local/lib/python3.12/site-packages`. The shell script is also where I
can specify which tickers I want updated, from which sources, as well as my
Alpha Vantage key.

### Requirements

The Python code uses

* BeautifulSoup (https://beautiful-soup-4.readthedocs.io/en/latest/)
* Requests (https://requests.readthedocs.io/)
* yfinance (https://ranaroussi.github.io/yfinance)
* and the gnucash Python library.

For Debian Linux based systems, BeautifulSoup and Requests should be available
in the distribution sources, possible as python3-bs4 and python3-requests. The
Python interface for GnuCash should also be available, possibly as
python3-gnucash.

That leaves yfinance. I have it installed with
`pip install --break-system-packages yfinance` but feel free to use an
environment manager and install it in that.

### Usage

Running `gnucash_prices.py -h` will provide the parameters, but the key items
are:

* `-a AlphaVantage_key` -- Only needed to use Alpha Vantage as a data source.
    The ALPHAVANTAGE_API_KEY environment variable can also be used.
* `/path/to/file.gnucash` -- The GnuCash data file to update with new pricing.
* `TICKER[:Y|A|M|*] [TICKER[:Y|A|M|*] ....] -- Investment identifers to update,
    with an optionally specified data source.

The data sources are, in searched order:

* Y -- Yahoo
* A -- Alpha Vantage, and only used if a key is provided.
* M -- Morningstar
* * -- First available, which is also the default.

# License

The code and documentation in this project is shareable under the terms of the
Creative Commons Attribution-ShareAlike 4.0 International Public License. See
the LICENSE.txt file for the contents of the license.
