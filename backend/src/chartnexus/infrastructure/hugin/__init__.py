"""HUGIN infrastructure adapters — the bridges that live outside the context.

The ``hugin`` context imports only ``build_hugin`` from here; every cross-context
read and every framework dependency is assembled in this package, keeping the
context free of infrastructure edges (enforced by ``task arch`` + ``lint-imports``).
"""

from __future__ import annotations
