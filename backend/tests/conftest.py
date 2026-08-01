"""Test-suite-wide isolation.

Settings read ``backend/.env`` at construction time. Without this fixture a
developer's local file leaks into assertions, so the suite passes on their
machine and fails in CI (or worse, the reverse).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path_factory) -> Iterator[None]:  # type: ignore[no-untyped-def]
    for key in list(os.environ):
        if key.startswith("MC_"):
            monkeypatch.delenv(key, raising=False)

    # Settings resolve `.env` relative to the working directory; pointing that
    # at an empty directory removes the file without touching the developer's.
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
    yield
