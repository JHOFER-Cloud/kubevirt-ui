"""Docs pages come from labelled ConfigMaps in the system namespace."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient


def _cm(name: str, data: dict[str, str] | None) -> SimpleNamespace:
    return SimpleNamespace(metadata=SimpleNamespace(name=name), data=data)


def _serve(mock_k8s_client: MagicMock, *configmaps: SimpleNamespace) -> None:
    mock_k8s_client.core_api.list_namespaced_config_map = AsyncMock(
        return_value=SimpleNamespace(items=list(configmaps)),
    )


def test_lists_only_labelled_configmaps_in_the_system_namespace(
    client: TestClient, mock_k8s_client: MagicMock,
) -> None:
    _serve(mock_k8s_client)
    assert client.get("/api/v1/docs").json() == {"pages": []}
    mock_k8s_client.core_api.list_namespaced_config_map.assert_awaited_once_with(
        namespace="kubevirt-ui-system", label_selector="kubevirt-ui.io/docs=true",
    )


def test_pages_sort_by_key_across_configmaps_and_drop_the_order_prefix(
    client: TestClient, mock_k8s_client: MagicMock,
) -> None:
    _serve(
        mock_k8s_client,
        _cm("b", {"20-dns.md": "# DNS\n\ntext", "10-ssh.md": "# SSH access\n"}),
        _cm("a", {"30-ingress.md": "no heading"}),
        _cm("empty", None),
    )
    pages = client.get("/api/v1/docs").json()["pages"]
    assert [(p["slug"], p["title"]) for p in pages] == [
        ("ssh", "SSH access"),
        ("dns", "DNS"),
        ("ingress", "Ingress"),
    ]
    assert pages[1]["content"] == "# DNS\n\ntext"


def test_a_slug_defined_twice_keeps_the_first_key(
    client: TestClient, mock_k8s_client: MagicMock,
) -> None:
    _serve(mock_k8s_client, _cm("a", {"10-ssh.md": "# First", "20-ssh.md": "# Second"}))
    assert [p["title"] for p in client.get("/api/v1/docs").json()["pages"]] == ["First"]
