"""The domain layer must not know how anything is stored or transported."""

from __future__ import annotations

import pytest

from tests.architecture.conftest import SRC, assert_no_imports, python_files

pytestmark = pytest.mark.architecture

VENDOR_PACKAGES = (
    "sqlalchemy",
    "fastapi",
    "starlette",
    "redis",
    "celery",
    "httpx",
    "alembic",
    "uvicorn",
    "anthropic",
    "openai",
)


def test_shared_domain_imports_no_vendor_packages() -> None:
    assert_no_imports(
        python_files("shared_kernel/domain"),
        VENDOR_PACKAGES,
        reason="shared_kernel.domain must stay free of framework and driver imports",
    )


def test_shared_domain_imports_no_infrastructure() -> None:
    assert_no_imports(
        python_files("shared_kernel/domain"),
        ("marketcompass.infrastructure", "marketcompass.entrypoints", "marketcompass.bootstrap"),
        reason="shared_kernel.domain must not depend on outer layers",
    )


def test_context_domain_modules_import_no_vendor_packages() -> None:
    """Each context's own ``domain/`` package is held to the same rule."""
    domain_dirs = [
        path.relative_to(SRC).as_posix()
        for path in (SRC / "contexts").glob("*/domain")
        if path.is_dir()
    ]
    assert_no_imports(
        python_files(*domain_dirs),
        VENDOR_PACKAGES,
        reason="context domain packages must stay free of framework and driver imports",
    )
