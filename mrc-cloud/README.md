# MRC Cloud Cockpit

Online PAPER trading cockpit for BTCUSDT and ETHUSDT.

Uses only Binance public USD-M endpoints. No exchange credentials are embedded or required.
It detects the first 15m boundary test of the previous completed UTC-hour range, classifies acceptance/rejection, overlays taker flow, open-interest change, top-trader positioning and funding, then produces LONG / SHORT / NO_TRADE plus an experimental risk plan. Qualified signals are paper-executed and journaled in SQLite.

This is an operational research system, not a guarantee of positive expected return.
