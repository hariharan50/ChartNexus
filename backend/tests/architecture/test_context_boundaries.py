"""Bounded contexts talk through events and published contracts, not imports."""

from __future__ import annotations

import pytest

from tests.architecture.conftest import SRC, imports_in, python_files

pytestmark = pytest.mark.architecture

CONTEXT_ROOT = "chartnexus.contexts"


def _context_names() -> list[str]:
    return sorted(
        path.name
        for path in (SRC / "contexts").iterdir()
        if path.is_dir() and not path.name.startswith("_")
    )


def test_contexts_exist() -> None:
    assert _context_names(), "no bounded contexts found — has the tree moved?"


def test_no_context_imports_another_context() -> None:
    violations: list[str] = []

    for context in _context_names():
        others = {other for other in _context_names() if other != context}
        for path in python_files(f"contexts/{context}"):
            for site in imports_in(path):
                if not site.module.startswith(f"{CONTEXT_ROOT}."):
                    continue
                imported = site.module.removeprefix(f"{CONTEXT_ROOT}.").split(".", 1)[0]
                if imported in others:
                    violations.append(f"{context} -> {imported} ({path.name}:{site.line})")

    if violations:
        listing = "\n  ".join(violations)
        pytest.fail(
            "bounded contexts must integrate through domain events or a published\n"
            "port, never by importing each other's internals:\n  " + listing,
            pytrace=False,
        )
