"""API latency monitor — the capture half.

Every outbound HTTP call ChartNexus makes (Kite, FYERS, NSE, Yahoo, Telegram, …)
goes through the one ``httpx.AsyncClient`` the container builds, so a single
wrapping transport here measures all of them without touching any adapter.

Calls are counted in memory and flushed to Redis every few seconds, which is
what lets every process (API, ingest, Trade Buddy) feed one shared picture.
The read half lives in ``contexts/api_monitor``; the Redis layout both sides
agree on is :mod:`.schema`.
"""
