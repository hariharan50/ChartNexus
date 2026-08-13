"""Vendor SDKs stay behind their adapter.

The point of the adapter directories is that swapping Fyers for another broker,
or Anthropic for OpenAI, touches one folder. A stray ``import fyers_apiv3`` in a
handler quietly undoes that.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.architecture.conftest import SRC, imports_in

pytestmark = pytest.mark.architecture

# vendor package prefix -> the only directory allowed to import it
CONFINED_VENDORS: dict[str, str] = {
    "fyers_apiv3": "infrastructure/brokers/fyers",
    # The AI Console's LLM stack (LangGraph + LangChain + the Anthropic model)
    # stays behind the agent adapter, so swapping the framework or provider is
    # one folder.
    "langgraph": "infrastructure/agent",
    "langchain_core": "infrastructure/agent",
    "langchain_anthropic": "infrastructure/agent",
    "celery": "infrastructure/messaging/celery",
    "argon2": "infrastructure/security",
    "jwt": "infrastructure/security",
}


def _allowed(path: Path, permitted_dir: str) -> bool:
    return permitted_dir in path.relative_to(SRC).as_posix()


@pytest.mark.parametrize(("vendor", "permitted_dir"), sorted(CONFINED_VENDORS.items()))
def test_vendor_import_is_confined_to_its_adapter(vendor: str, permitted_dir: str) -> None:
    violations = [
        f"{path.relative_to(SRC).as_posix()}:{site.line}"
        for path in SRC.rglob("*.py")
        for site in imports_in(path)
        if (site.module == vendor or site.module.startswith(f"{vendor}."))
        and not _allowed(path, permitted_dir)
    ]

    if violations:
        listing = "\n  ".join(violations)
        pytest.fail(
            f"{vendor!r} may only be imported under {permitted_dir}/:\n  {listing}",
            pytrace=False,
        )
