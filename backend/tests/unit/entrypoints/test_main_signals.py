"""The signals CLI end-to-end on a temp dataset: fit writes a loadable artifact,
backtest reports on it — all offline, no database."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chartnexus.contexts.signals.domain.ensemble import ModelArtifact
from chartnexus.contexts.signals.domain.models import Horizon
from chartnexus.entrypoints import main_signals

pytestmark = pytest.mark.unit


def _write_dataset(path: Path) -> None:
    lines: list[str] = []
    for k in range(-40, 41):
        if k == 0:
            continue
        x = k / 40.0
        lines.append(
            json.dumps(
                {"horizon": "intraday", "features": {"ret_5": x}, "label": 1 if x > 0 else 0}
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def test_fit_writes_a_loadable_artifact(tmp_path: Path) -> None:
    dataset = tmp_path / "data.jsonl"
    out = tmp_path / "artifact.json"
    _write_dataset(dataset)

    code = main_signals._main(
        ["fit", "--dataset", str(dataset), "--out", str(out), "--epochs", "300"]
    )
    assert code == 0
    assert out.is_file()

    artifact = ModelArtifact.from_dict(json.loads(out.read_text(encoding="utf-8")))
    intraday = artifact.models[Horizon.INTRADAY]
    assert intraday.weights["ret_5"] > 0.0
    assert intraday.calibration  # a calibration table was fitted


def test_backtest_reports_on_the_fitted_artifact(tmp_path: Path) -> None:
    dataset = tmp_path / "data.jsonl"
    out = tmp_path / "artifact.json"
    _write_dataset(dataset)
    main_signals._main(["fit", "--dataset", str(dataset), "--out", str(out)])

    code = main_signals._main(["backtest", "--dataset", str(dataset), "--model", str(out)])
    assert code == 0

    report = main_signals._backtest(dataset, out)
    assert report["intraday"]["directional_accuracy"] == 1.0


def test_missing_dataset_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main_signals._main(["backtest", "--dataset", str(tmp_path / "nope.jsonl")])
    assert code == 2
    assert "not found" in capsys.readouterr().err
