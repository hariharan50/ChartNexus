"""API monitor: how many outbound calls ChartNexus makes, to whom, and how fast.

Read side only. The calls are captured by the transport in
``infrastructure/observability/api_monitor``; this context turns the stored
counters into the admin overview and each user's view of their own broker.
"""
