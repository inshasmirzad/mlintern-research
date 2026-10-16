import pytest
from fastapi.testclient import TestClient
from main import app
import uuid
import json

client = TestClient(app)

def test_liveness_probe_bypasses_middleware():
    """Test that /health/live works and does not require or generate X-Request-ID."""
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    # Should bypass middleware, so no X-Request-ID injected
    assert "X-Request-ID" not in response.headers

def test_tracing_middleware_generates_id():
    """Test that middleware generates a UUID if none is provided."""
    response = client.get("/health/ready")
    assert "X-Request-ID" in response.headers
    val = response.headers["X-Request-ID"]
    uuid.UUID(val)

def test_tracing_middleware_preserves_inbound_id():
    """Test that middleware preserves an inbound X-Request-ID."""
    test_id = "test-request-id-123"
    response = client.get("/health/ready", headers={"X-Request-ID": test_id})
    assert response.headers["X-Request-ID"] == test_id

def test_http_exception_handler():
    """Test that HTTPException returns expected status with request_id."""
    response = client.get("/nonexistent-route-for-404")
    assert response.status_code == 404
    data = response.json()
    assert "request_id" in data
    assert data["detail"] == "Not Found"
