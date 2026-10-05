"""Only the composition roots may wire concrete adapters together."""

from __future__ import annotations

import pytest

from tests.architecture.conftest import assert_no_imports, python_files

pytestmark = pytest.mark.architecture


def test_infrastructure_does_not_import_entrypoints() -> None:
    assert_no_imports(
        python_files("infrastructure"),
        ("chartnexus.entrypoints",),
        reason="infrastructure is a dependency of the entrypoints, never the reverse",
    )


def test_infrastructure_does_not_import_the_container() -> None:
    """Adapters take their dependencies as constructor arguments.

    Reaching for the container from inside an adapter turns it into a service
    locator and makes the adapter untestable without a full process.
    """
    assert_no_imports(
        python_files("infrastructure"),
        ("chartnexus.bootstrap.container",),
        reason="adapters must receive dependencies, not fetch them from the container",
    )


def test_contexts_do_not_import_entrypoints() -> None:
    assert_no_imports(
        python_files("contexts"),
        ("chartnexus.entrypoints", "chartnexus.bootstrap"),
        reason="bounded contexts must not depend on process wiring",
    )
