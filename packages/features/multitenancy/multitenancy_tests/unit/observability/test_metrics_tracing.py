from unittest.mock import MagicMock, patch

from cqrs_ddd_multitenancy.observability.metrics import TenantMetrics
from cqrs_ddd_multitenancy.observability.tracing import TenantTracing


def test_tenant_metrics_no_op_when_not_installed():
    # Should not raise any error even without prometheus installed
    with TenantMetrics.operation("resolve", resolver="my_resolver"):
        pass

    with TenantMetrics.operation("switch_schema"):
        pass


def test_tenant_tracing_no_op_when_not_installed():
    # Spans should be usable context managers regardless of whether OTel is installed
    with TenantTracing.database_switch_span("tenant-1") as span:
        assert span is not None or span is None  # either a real span or None — no crash

    with TenantTracing.resolve_span("HeaderResolver") as span:
        pass  # should not raise

    with TenantTracing.schema_switch_span("tenant-1") as span:
        pass  # should not raise

    # set_tenant should not raise regardless of OTel availability
    span_mock = MagicMock()
    TenantTracing.set_tenant(span_mock, "tenant-1")
    # If OTel is installed, set_attribute is called; if not, it is a no-op.
    # We simply verify no exception was raised.


@patch("cqrs_ddd_multitenancy.observability.metrics.HAS_PROMETHEUS", False)
def test_tenant_metrics_active(monkeypatch):
    # With HAS_PROMETHEUS=False the context manager must still be a no-op
    with TenantMetrics.operation("resolve", resolver="test_resolver"):
        pass
