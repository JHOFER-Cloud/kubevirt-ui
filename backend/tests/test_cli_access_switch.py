"""CLI_ACCESS_ENABLED=false hides CLI Access and refuses kubeconfigs."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


def test_on_by_default(client: TestClient) -> None:
    assert client.get("/api/v1/features").json()["cliAccess"] is True


def test_off_hides_and_refuses(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "cli_access_enabled", False)
    assert client.get("/api/v1/features").json()["cliAccess"] is False
    response = client.post("/api/v1/auth/kubeconfig", json={})
    assert response.status_code == 404
    assert response.json()["detail"] == "CLI access is disabled"
