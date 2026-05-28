"""
Tests for GET /insights/* endpoints.

Service functions are patched so the macro-summary tests stay isolated
from the DB. The detection-quality tests exercise the real service
against the bundled detection_quality.json fixture except where the
contract-verdict math is being asserted, where the underlying loader
is mocked to inject specific recall/FPR values.
"""
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.schemas.economic import KeyIndicator, SummaryOut
from app.services import insights as insights_svc

SVC = "app.services.economic"


def _indicator(**kwargs) -> KeyIndicator:
    defaults = dict(
        series_id="CPIAUCSL", series_name="Consumer Price Index", source="BLS",
        latest_date=date(2024, 6, 1), latest_value=3.5,
    )
    return KeyIndicator(**{**defaults, **kwargs})


# ---------------------------------------------------------------------------
# GET /insights/summary
# ---------------------------------------------------------------------------

def test_summary_returns_200(client):
    with patch(f"{SVC}.get_summary", return_value=SummaryOut(indicators=[])):
        resp = client.get("/insights/summary")
    assert resp.status_code == 200


def test_summary_has_indicators_key(client):
    with patch(f"{SVC}.get_summary", return_value=SummaryOut(indicators=[])):
        resp = client.get("/insights/summary")
    data = resp.json()
    assert "indicators" in data
    assert isinstance(data["indicators"], list)


def test_summary_indicator_shape(client):
    with patch(f"{SVC}.get_summary", return_value=SummaryOut(indicators=[_indicator()])):
        resp = client.get("/insights/summary")
    item = resp.json()["indicators"][0]
    for field in ("series_id", "series_name", "source", "latest_date", "latest_value"):
        assert field in item, f"Missing field: {field}"


def test_summary_values_correct(client):
    ind = _indicator(latest_date=date(2024, 6, 1), latest_value=3.5)
    with patch(f"{SVC}.get_summary", return_value=SummaryOut(indicators=[ind])):
        resp = client.get("/insights/summary")
    item = resp.json()["indicators"][0]
    assert item["latest_date"] == "2024-06-01"
    assert float(item["latest_value"]) == 3.5


# ---------------------------------------------------------------------------
# GET /insights/detection-quality
# ---------------------------------------------------------------------------

DQ_SVC = "app.services.insights"


@pytest.fixture(autouse=True)
def _clear_dq_cache():
    """Clear the JSON read cache around every detection-quality test
    so a patched loader is not shadowed by a prior call's cached
    value."""
    insights_svc._clear_detection_quality_cache()
    yield
    insights_svc._clear_detection_quality_cache()


def _fake_raw(recall: float = 0.45, fpr: float = 0.05) -> dict:
    """A minimal valid detection_quality.json payload with overridable
    recall and FPR so contract-verdict tests can hit both branches."""
    return {
        "global": {
            "injected_pairs": 100,
            "matched_pairs": int(round(recall * 100)),
            "recall": recall,
        },
        "by_anomaly_type": {
            "missing_department": {
                "injected": 10, "matched": 10, "recall": 1.0,
            },
        },
        "false_positive_rate": fpr,
        "false_positives": 5,
        "negative_universe": 100,
        "flag_rate": 0.1,
        "total_flags": 20,
        "total_metric_rows": 200,
    }


def test_detection_quality_endpoint_returns_200(client):
    """Structural: the endpoint is mounted, the bundled fixture loads,
    and a 200 comes back. Catches wiring errors without asserting
    specific values."""
    resp = client.get("/insights/detection-quality")
    assert resp.status_code == 200


def test_detection_quality_has_per_anomaly_type_block(client):
    """Structural: by_anomaly_type is non-empty and shaped as the
    portal expects (dict keyed by type name with injected/matched/
    recall fields per entry)."""
    body = client.get("/insights/detection-quality").json()
    assert isinstance(body["by_anomaly_type"], dict)
    assert body["by_anomaly_type"], "expected at least one anomaly-type entry"
    sample = next(iter(body["by_anomaly_type"].values()))
    for field in ("injected", "matched", "recall"):
        assert field in sample


def test_detection_quality_returns_global_recall_from_fixture(client):
    """Business-correctness: the endpoint's recall equals the raw
    value read independently from the bundled JSON. Catches silent
    transforms in the load/serve path."""
    fixture_path = Path(settings.resolved_detection_quality_path)
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))

    body = client.get("/insights/detection-quality").json()

    assert body["global"]["recall"] == raw["global"]["recall"]
    assert body["false_positive_rate"] == raw["false_positive_rate"]
    assert body["global"]["injected_pairs"] == raw["global"]["injected_pairs"]
    assert body["global"]["matched_pairs"] == raw["global"]["matched_pairs"]


def test_detection_quality_passes_contract_when_metrics_above_thresholds(client):
    """Business-correctness: recall=0.45, fpr=0.05 satisfies the
    phase 2 contract (recall>=0.35, fpr<=0.10) - passes=True and no
    reasons."""
    with patch(
        f"{DQ_SVC}._load_detection_quality_cached",
        return_value=_fake_raw(recall=0.45, fpr=0.05),
    ):
        body = client.get("/insights/detection-quality").json()
    assert body["contract"]["passes"] is True
    assert body["contract"]["reasons"] == []
    assert body["contract"]["global_recall_threshold"] == 0.35
    assert body["contract"]["fpr_threshold"] == 0.10


def test_detection_quality_fails_contract_when_recall_below_threshold(client):
    """Business-correctness: recall=0.30 trips the recall reason and
    only that reason. The portal renders these strings verbatim."""
    with patch(
        f"{DQ_SVC}._load_detection_quality_cached",
        return_value=_fake_raw(recall=0.30, fpr=0.05),
    ):
        body = client.get("/insights/detection-quality").json()
    assert body["contract"]["passes"] is False
    assert len(body["contract"]["reasons"]) == 1
    assert "recall" in body["contract"]["reasons"][0].lower()


def test_detection_quality_fails_contract_when_fpr_above_threshold(client):
    """Business-correctness: matches the current canonical state -
    recall passes, FPR fails - so the portal-side failure path is
    exercised against the actual production scenario."""
    with patch(
        f"{DQ_SVC}._load_detection_quality_cached",
        return_value=_fake_raw(recall=0.48, fpr=0.19),
    ):
        body = client.get("/insights/detection-quality").json()
    assert body["contract"]["passes"] is False
    assert any("false_positive_rate" in r for r in body["contract"]["reasons"])


def test_detection_quality_cache_avoids_repeated_disk_reads(client):
    """Structural: a second hit reuses the cached JSON. Asserted by
    counting Path.read_text calls on the resolved fixture - cache hit
    means the second request reads nothing from disk."""
    fixture_path = Path(settings.resolved_detection_quality_path)
    fixture_text = fixture_path.read_text(encoding="utf-8")

    call_count = {"n": 0}
    original_read_text = Path.read_text

    def counting_read_text(self, *args, **kwargs):
        if Path(self).resolve() == fixture_path.resolve():
            call_count["n"] += 1
            return fixture_text
        return original_read_text(self, *args, **kwargs)

    with patch.object(Path, "read_text", counting_read_text):
        client.get("/insights/detection-quality")
        client.get("/insights/detection-quality")
        client.get("/insights/detection-quality")
    assert call_count["n"] == 1, (
        f"expected the cached loader to read the fixture once, "
        f"got {call_count['n']} reads"
    )
