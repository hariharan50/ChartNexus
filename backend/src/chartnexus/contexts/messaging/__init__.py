"""Messaging — outbound delivery of updates to a user's own channels.

Each user connects their own messaging channel (Telegram now; WhatsApp later) and
ChartNexus pushes updates to it — the MME100 pre-market briefing to begin with.
The context is provider-agnostic: the domain knows a ``Channel`` and a
``MessageSenderPort``, and infrastructure supplies the per-channel adapter.

Like the sibling contexts it never imports another context; the delivery trigger is
composed in the worker entrypoint, and cross-context/HTTP wiring lives behind the
``infrastructure/messaging`` bridge.
"""
