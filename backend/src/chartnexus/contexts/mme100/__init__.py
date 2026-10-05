"""MME100 — "Market Made Easy 100%".

A per-user, LLM-connected market-analysis agent for the AI Console. Its single
skill is a disciplined Indian pre-market analysis framework (global cues → India
outlook → sectors → stocks to watch → events → risks). Unlike HELLA/STRYX it may
also read live global cues off the web, and it runs an autonomous pre-market
briefing each trading morning for tenants that opt in.

Like the sibling agents, MME100 is its own bounded context: it never imports
another context, reaches live market data only through the sanctioned
``infrastructure/agent`` bridge, and is LLM-only (the tab is disabled without a
per-user key).
"""
