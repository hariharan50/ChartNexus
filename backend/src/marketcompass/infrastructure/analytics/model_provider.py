"""Supplies the signals engine its calibrated model artifact.

Loads a fitted artifact from ``MC_SIGNALS_MODEL_PATH`` when that JSON exists (the
backtest CLI writes it), otherwise falls back to the hand-set default so the
engine always runs. The load is cached per process — the artifact is small and
changes only when re-fitted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from marketcompass.contexts.signals.domain import ensemble
from marketcompass.contexts.signals.domain.ensemble import ModelArtifact
from marketcompass.infrastructure.observability.structured_logging import get_logger

log = get_logger(__name__)


class ModelProvider:
    """Implements the signals ``ModelPort``."""

    def __init__(self, artifact_path: str | None = None) -> None:
        self._path = artifact_path or os.environ.get("MC_SIGNALS_MODEL_PATH")
        self._cached: ModelArtifact | None = None

    def artifact(self) -> ModelArtifact:
        if self._cached is not None:
            return self._cached
        self._cached = self._load()
        return self._cached

    def _load(self) -> ModelArtifact:
        if not self._path:
            return ensemble.default_artifact()
        path = Path(self._path)
        if not path.is_file():
            log.info("signals_model_default", reason="no_artifact_file", path=self._path)
            return ensemble.default_artifact()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ModelArtifact.from_dict(data)
        except (OSError, ValueError, KeyError) as exc:
            log.warning("signals_model_load_failed", path=self._path, error=repr(exc))
            return ensemble.default_artifact()
