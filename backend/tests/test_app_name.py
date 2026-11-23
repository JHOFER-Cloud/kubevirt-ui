"""The UI name comes from APP_NAME, readable before login via /features."""

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import router as router_module


def test_features_carry_the_default_name(client: TestClient) -> None:
    assert client.get("/api/v1/features").json()["appName"] == "KubeVirt UI"


def test_features_carry_a_configured_name(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(router_module.settings, "app_name", "Virtshaus")
    assert client.get("/api/v1/features").json()["appName"] == "Virtshaus"
