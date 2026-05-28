"""Response schemas for the /insights/* endpoints whose payload
shape is owned by the ETL artifact rather than a relational table.

The macro-economic /insights/summary endpoint reads its shape from
app.schemas.economic; the grocery-detection /insights/detection-quality
endpoint reads its shape from the ETL's detection_quality.json artifact,
which lives here so the detection-quality field names (some Python
keywords, some computed by the service) stay separate from the row
schemas in app.schemas.grocery.
"""
from pydantic import BaseModel, ConfigDict, Field


class GlobalMetricsOut(BaseModel):
    """The global block of detection_quality.json."""

    injected_pairs: int
    matched_pairs: int
    recall: float


class AnomalyTypeStatsOut(BaseModel):
    """Per-anomaly-type recall stats from detection_quality.json."""

    injected: int
    matched: int
    recall: float


class ContractOut(BaseModel):
    """The phase 2 detection contract verdict computed by the service
    from the raw JSON's recall and FPR against the platform's
    thresholds. Lifted out of the JSON so the portal can render
    pass/fail without re-knowing the thresholds."""

    global_recall_threshold: float
    fpr_threshold: float
    passes: bool
    reasons: list[str]


class DetectionQualityOut(BaseModel):
    """Detection-quality measurement payload.

    Mirrors the shape evaluate_detection.py writes, plus a computed
    contract verdict. The ``global_`` alias is required because
    ``global`` is a Python keyword and cannot be a field name; the
    serialized JSON exposes it as ``global``.
    """

    model_config = ConfigDict(populate_by_name=True)

    global_: GlobalMetricsOut = Field(alias="global")
    by_anomaly_type: dict[str, AnomalyTypeStatsOut]
    false_positive_rate: float
    false_positives: int
    negative_universe: int
    flag_rate: float
    total_flags: int
    total_metric_rows: int
    contract: ContractOut
