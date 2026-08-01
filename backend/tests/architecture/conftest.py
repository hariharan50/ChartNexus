"""Shared helpers for the architecture suite.

These tests read source with :mod:`ast` rather than importing it: an import
would execute module-level code, and a rule violation should be reported as a
failure, not as an ImportError during collection.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "marketcompass"


@dataclass(frozen=True, slots=True)
class ImportSite:
    module: str
    path: Path
    line: int

    def __str__(self) -> str:
        return f"{self.path.name}:{self.line} imports {self.module}"


def python_files(*relative: str) -> Iterator[Path]:
    for part in relative:
        root = SRC / part
        if not root.exists():
            continue
        yield from root.rglob("*.py")


def imports_in(path: Path) -> Iterator[ImportSite]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield ImportSite(alias.name, path, node.lineno)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield ImportSite(node.module, path, node.lineno)


def assert_no_imports(
    files: Iterator[Path],
    forbidden: tuple[str, ...],
    *,
    reason: str,
) -> None:
    violations = [
        site
        for path in files
        for site in imports_in(path)
        if any(site.module == name or site.module.startswith(f"{name}.") for name in forbidden)
    ]
    if violations:
        listing = "\n  ".join(str(violation) for violation in violations)
        pytest.fail(f"{reason}\n  {listing}", pytrace=False)
