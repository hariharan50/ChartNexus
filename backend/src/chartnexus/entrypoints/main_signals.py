"""Fit and evaluate the signals ensemble — ``chartnexus-signals {fit|backtest}``.

Both commands work off a **dataset file** (JSONL, one example per line):

    {"horizon": "intraday", "features": {"ret_5": 0.3, ...}, "label": 1}

Keeping the CLI dataset-driven means the whole fit/score loop runs offline with
no database and no new dependency — the maths lives in the pure
:mod:`signals.domain.training` and :mod:`signals.domain.labeling` modules.

* ``fit`` — fits logistic weights + a calibration table per horizon and writes a
  :class:`ModelArtifact` JSON. Point ``CN_SIGNALS_MODEL_PATH`` at it and the live
  engine loads it instead of the hand-set defaults.
* ``backtest`` — replays a dataset through an artifact (the defaults, or one
  passed with ``--model``) and prints per-horizon accuracy, coverage, Brier and a
  calibration curve.

Producing a dataset from the intraday archive (historical feature + forward-label
replay) is the remaining data-plumbing step; it is deferred alongside the
persisted feature store. Until then, feed this CLI any dataset in the format
above.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from chartnexus.contexts.signals.domain.ensemble import (
    HorizonModel,
    ModelArtifact,
    _band,
    default_artifact,
)
from chartnexus.contexts.signals.domain.features import FEATURE_NAMES
from chartnexus.contexts.signals.domain.models import Decision, Horizon
from chartnexus.contexts.signals.domain.training import (
    LabeledRow,
    backtest,
    build_calibration,
    fit_logistic,
)
from chartnexus.shared_kernel.domain import indicators as ind

# Fraction of each horizon's rows (taken from the end) held out to fit the
# calibration table, so confidence is not calibrated on the same rows it trained.
_CALIBRATION_SPLIT = 0.3


class DatasetError(RuntimeError):
    """The dataset file was missing, empty, or malformed."""


def _load(path: Path) -> dict[Horizon, list[LabeledRow]]:
    if not path.is_file():
        raise DatasetError(f"dataset not found: {path}")
    by_horizon: dict[Horizon, list[LabeledRow]] = defaultdict(list)
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            horizon = Horizon(record["horizon"])
            features = {str(k): float(v) for k, v in record["features"].items()}
            label = int(record["label"])
        except (ValueError, KeyError, TypeError) as exc:
            raise DatasetError(f"bad row at line {lineno}: {exc}") from exc
        by_horizon[horizon].append(LabeledRow(features=features, label=label))
    if not by_horizon:
        raise DatasetError(f"dataset is empty: {path}")
    return dict(by_horizon)


def _fit(dataset: Path, out: Path, *, epochs: int) -> dict[str, object]:
    by_horizon = _load(dataset)
    base = default_artifact()
    models = dict(base.models)
    summary: dict[str, object] = {}

    for horizon, rows in by_horizon.items():
        cut = max(1, int(len(rows) * (1.0 - _CALIBRATION_SPLIT)))
        train, calib = rows[:cut], rows[cut:]
        try:
            model = fit_logistic(train, FEATURE_NAMES, epochs=epochs)
        except ValueError as exc:
            summary[horizon.value] = {"skipped": str(exc), "rows": len(rows)}
            continue

        calib_rows = calib or train
        scored = [
            (min(1.0, abs(_prob(model, row) - 0.5) * 2.0), _hit(model, row)) for row in calib_rows
        ]
        table = build_calibration([(s, h) for s, h in scored if h is not None])
        models[horizon] = HorizonModel(
            weights=model.weights, bias=model.bias, band=model.band, calibration=table
        )
        summary[horizon.value] = {"rows": len(rows), "calibration_points": len(table)}

    artifact = ModelArtifact(
        models=models,
        trained_at=datetime.now(UTC).isoformat(),
        data_range=f"fit from {dataset.name}",
        metrics=summary,
    )
    out.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")
    return summary


def _prob(model: HorizonModel, row: LabeledRow) -> float:
    z = model.bias + sum(w * row.features.get(n, 0.0) for n, w in model.weights.items())
    return ind.sigmoid(z)


def _hit(model: HorizonModel, row: LabeledRow) -> int | None:
    """1/0 when the call is decisive and right/wrong; ``None`` when it's a HOLD."""
    decision = _band(_prob(model, row), model.band)
    if decision is Decision.HOLD:
        return None
    predicted_up = decision is Decision.BUY
    return int(predicted_up == (row.label == 1))


def _backtest(dataset: Path, model_path: Path | None) -> dict[str, object]:
    by_horizon = _load(dataset)
    artifact = _load_artifact(model_path)
    report: dict[str, object] = {}
    for horizon, rows in by_horizon.items():
        model = artifact.models.get(horizon)
        if model is None:
            report[horizon.value] = {"skipped": "no model for horizon"}
            continue
        report[horizon.value] = backtest(rows, model, FEATURE_NAMES)
    return report


def _load_artifact(path: Path | None) -> ModelArtifact:
    if path is None:
        return default_artifact()
    if not path.is_file():
        raise DatasetError(f"model artifact not found: {path}")
    return ModelArtifact.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chartnexus-signals", description="Fit and evaluate the signals ensemble."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fit = sub.add_parser("fit", help="fit weights + calibration, write a model artifact")
    fit.add_argument("--dataset", required=True, metavar="FILE.jsonl")
    fit.add_argument("--out", required=True, metavar="ARTIFACT.json")
    fit.add_argument("--epochs", type=int, default=400)

    bt = sub.add_parser("backtest", help="replay a dataset through a model, print metrics")
    bt.add_argument("--dataset", required=True, metavar="FILE.jsonl")
    bt.add_argument("--model", metavar="ARTIFACT.json", help="defaults to the hand-set artifact")

    return parser


def _main(argv: list[str]) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "fit":
            summary = _fit(Path(args.dataset), Path(args.out), epochs=args.epochs)
            print(json.dumps({"wrote": args.out, "horizons": summary}, indent=2))
        else:
            model_path = Path(args.model) if args.model else None
            print(json.dumps(_backtest(Path(args.dataset), model_path), indent=2))
    except DatasetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def run() -> None:
    """Console-script entrypoint: ``uv run chartnexus-signals fit ...``."""
    raise SystemExit(_main(sys.argv[1:]))


if __name__ == "__main__":
    run()
