"""Report — the daily market report (multi-page branded PDF).

Assembles a per-user daily market report from deterministic data (market_data,
options_analytics) plus MME100's narrative, renders it to a branded PDF, and
delivers it on the user's schedule (reusing the messaging channel).

Design rule: every number/table/chart comes from a data tool; the LLM writes only
the prose commentary, grounded in those numbers — so a paid report never carries a
hallucinated figure. Per-user / per-tenant like every other context; the LLM runs
on the user's own key.
"""
