from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.api.routes import beta, market
from backend.core.user_rate_limiter import UserRateLimiter


def test_market_product_config_exposes_free_beta_mode():
    app = FastAPI()
    app.include_router(market.router, prefix="/api")
    client = TestClient(app)

    response = client.get("/api/market/product-config")
    assert response.status_code == 200
    data = response.json()
    assert data["current_mode"] == "free_beta"
    assert data["beta_open"] is True
    assert isinstance(data["beta_notes"], list)
    assert data["target_audience"]


def test_beta_feedback_accepts_payload_with_optional_auth(monkeypatch):
    app = FastAPI()
    app.include_router(beta.router, prefix="/api")
    client = TestClient(app)

    monkeypatch.setattr(
        "backend.data.storage.supabase_client.create_beta_feedback",
        lambda payload: {"id": "fake-feedback-id", **payload},
    )

    response = client.post(
        "/api/beta/feedback",
        json={
            "category": "ux",
            "message": "首頁 CTA 可以再更明確一點，現在我第一眼還是要想一下。",
            "page": "dashboard",
            "rating": 4,
            "would_recommend": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["feedback_id"] == "fake-feedback-id"


def test_free_beta_effective_tier_promotes_free_users():
    limiter = UserRateLimiter()
    assert limiter._get_effective_tier("free") == "premium"
    assert limiter._get_effective_tier("pro") == "pro"
