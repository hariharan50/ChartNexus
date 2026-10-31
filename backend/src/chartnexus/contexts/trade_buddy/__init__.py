"""Trade Buddy — morning levels, watched live, alerted once.

The user marks six levels (S1-S3, R1-R3) before the open. Through the session a
watcher compares live price against each one and reports approaches, touches,
confirmed breaks, rejected wicks, reclaims and opening gaps — each exactly once,
to Telegram always and to WhatsApp only when the event is worth the budget.

Read-only: this context subscribes to market data and sends messages. It places
no orders and touches no execution endpoint.
"""
