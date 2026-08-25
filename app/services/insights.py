"""Service layer for /insights/* endpoints that read JSON artifacts
rather than relational data.

The detection_quality.json artifact is produced upstream by the ETL's
evaluate_detection.py and copied byte-identical into app/fixtures/.
This module loads it, computes the phase 2 contract verdict, and
returns a DetectionQualityOut. The contract thresholds live here
rather than in the JSON so the artifact stays a pure measurement;
the verdict is a derived view the API owns.
"""
import json
from functools import lru_cache
from pathlib import Path

import structlog

from app.core.config import settings
from app.core.metrics import service_call_total
from app.schemas.insights import (
    AnomalyTypeStatsOut,
    ContractOut,
    DetectionQualityOut,
    GlobalMetricsOut,
)

# Phase 2 detection contract. Matches CONTRACT_GLOBAL_RECALL and
# CONTRACT_FPR in the ETL's scripts/evaluate_detection.py - the same
# thresholds that script renders verbally in its stdout. Pinned here so
# the API can serve a passes/reasons verdict without re-reading the
# script.
CONTRACT_GLOBAL_RECALL = 0.35
CONTRACT_FPR = 0.10


logger = structlog.get_logger(__name__)


@lru_cache(maxsize=1)
def _load_detection_quality_cached(path: str) -> dict:
    """Read and parse the JSON artifact, keyed by resolved path so an
    env-var flip during tests naturally serves the new file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _clear_detection_quality_cache() -> None:
    """For tests that flip the resolved path and need a fresh read."""
    _load_detection_quality_cached.cache_clear()


def _evaluate_contract(global_recall: float, fpr: float) -> ContractOut:
    reasons: list[str] = []
    if global_recall < CONTRACT_GLOBAL_RECALL:
        reasons.append(
            f"global recall {global_recall:.3f} below threshold "
            f"{CONTRACT_GLOBAL_RECALL}"
        )
    if fpr > CONTRACT_FPR:
        reasons.append(
            f"false_positive_rate {fpr:.3f} above threshold {CONTRACT_FPR}"
        )
    return ContractOut(
        global_recall_threshold=CONTRACT_GLOBAL_RECALL,
        fpr_threshold=CONTRACT_FPR,
        passes=not reasons,
        reasons=reasons,
    )


def get_detection_quality() -> DetectionQualityOut:
    """Load detection_quality.json, compute the contract verdict, and
    return a DetectionQualityOut. Raises FileNotFoundError if the
    resolved path does not point at a readable file."""
    path = settings.resolved_detection_quality_path
    if not Path(path).is_file():
        raise FileNotFoundError(
            f"detection_quality.json not found at '{path}'."
        )
    logger.info("service_call_started", service="get_detection_quality")
    service_call_total.labels(service="get_detection_quality").inc()

    raw = _load_detection_quality_cached(path)

    global_block = raw["global"]
    contract = _evaluate_contract(
        global_recall=global_block["recall"],
        fpr=raw["false_positive_rate"],
    )

    payload = DetectionQualityOut(
        **{"global": GlobalMetricsOut(**global_block)},
        by_anomaly_type={
            k: AnomalyTypeStatsOut(**v) for k, v in raw["by_anomaly_type"].items()
        },
        false_positive_rate=raw["false_positive_rate"],
        false_positives=raw["false_positives"],
        negative_universe=raw["negative_universe"],
        flag_rate=raw["flag_rate"],
        total_flags=raw["total_flags"],
        total_metric_rows=raw["total_metric_rows"],
        contract=contract,
    )
    logger.info(
        "service_call_completed",
        service="get_detection_quality",
        contract_passes=contract.passes,
    )
    return payload
