"""A VM port is published as Service + Ingress, only for the namespace's allowed domains."""

from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from kubernetes_asyncio.client import ApiException

from app.api.v1.vm_publish import host_allowed, parse_domains

URL = "/api/v1/namespaces/vm-tenant2/vms/web/published"


def _ingress(name: str, host: str, svc: str, port: int, vm: str = "web") -> NS:
    backend = NS(service=NS(name=svc, port=NS(number=port)))
    return NS(
        metadata=NS(name=name, labels={"kubevirt-ui.io/vm": vm}),
        spec=NS(
            rules=[NS(host=host, http=NS(paths=[NS(backend=backend)]))],
            tls=[NS(secret_name=f"{name}-tls")],
        ),
    )


@pytest.fixture
def net(mock_k8s_client: MagicMock):
    mock_k8s_client.core_api.read_namespace = AsyncMock(return_value=NS(
        metadata=NS(annotations={"kubevirt-ui.io/allowed-domains": "example.com, foo.org"}),
    ))
    mock_k8s_client.custom_api.get_namespaced_custom_object = AsyncMock(
        return_value={"metadata": {"uid": "vm-uid"}},
    )
    mock_k8s_client.core_api.create_namespaced_service = AsyncMock()
    mock_k8s_client.core_api.delete_namespaced_service = AsyncMock()
    api = MagicMock()
    api.list_namespaced_ingress = AsyncMock(return_value=NS(items=[]))
    api.create_namespaced_ingress = AsyncMock()
    api.delete_namespaced_ingress = AsyncMock()
    with patch("app.api.v1.vm_publish.client.NetworkingV1Api", return_value=api):
        yield api


def test_allowed_domains_match_at_a_dot() -> None:
    domains = parse_domains({"kubevirt-ui.io/allowed-domains": " Example.com,,foo.org "})
    assert domains == ["example.com", "foo.org"]
    assert host_allowed("example.com", domains)
    assert host_allowed("www.example.com", domains)
    assert not host_allowed("evilexample.com", domains)
    assert not host_allowed("x.jhofer.org", domains)
    assert parse_domains(None) == []


def test_publish_creates_a_service_and_ingress_owned_by_the_vm(
    client: TestClient, net: MagicMock, mock_k8s_client: MagicMock,
) -> None:
    r = client.post(URL, json={"host": "WWW.Example.com", "port": 8080})
    assert r.status_code == 201, r.text
    assert r.json()["host"] == "www.example.com"

    svc = mock_k8s_client.core_api.create_namespaced_service.await_args.args[1]
    assert svc["metadata"]["name"] == "web-p8080"
    assert svc["spec"]["selector"] == {"vm.kubevirt.io/name": "web"}
    assert "type" not in svc["spec"]

    ing = net.create_namespaced_ingress.await_args.args[1]
    assert ing["metadata"]["name"] == "web-www-example-com"
    assert ing["spec"]["tls"] == [{"hosts": ["www.example.com"], "secretName": "web-www-example-com-tls"}]
    for obj in (svc, ing):
        assert obj["metadata"]["labels"] == {"kubevirt-ui.io/published": "true", "kubevirt-ui.io/vm": "web"}
        assert obj["metadata"]["ownerReferences"][0]["uid"] == "vm-uid"
    assert "annotations" not in ing["metadata"]


def test_a_host_outside_the_allowed_domains_is_refused(
    client: TestClient, net: MagicMock,
) -> None:
    r = client.post(URL, json={"host": "x.jhofer.org", "port": 80})
    assert r.status_code == 403
    assert "example.com, foo.org" in r.json()["detail"]
    net.create_namespaced_ingress.assert_not_awaited()


def test_a_host_published_twice_is_refused(client: TestClient, net: MagicMock) -> None:
    net.list_namespaced_ingress.return_value = NS(items=[_ingress("other", "foo.org", "other-p80", 80, "other")])
    assert client.post(URL, json={"host": "foo.org", "port": 80}).status_code == 409


def test_a_second_host_on_the_same_port_reuses_the_service(
    client: TestClient, net: MagicMock, mock_k8s_client: MagicMock,
) -> None:
    mock_k8s_client.core_api.create_namespaced_service.side_effect = ApiException(status=409)
    assert client.post(URL, json={"host": "foo.org", "port": 80}).status_code == 201
    net.create_namespaced_ingress.assert_awaited_once()


def test_unpublish_keeps_a_service_another_host_still_uses(
    client: TestClient, net: MagicMock, mock_k8s_client: MagicMock,
) -> None:
    a = _ingress("web-a-example-com", "a.example.com", "web-p80", 80)
    b = _ingress("web-b-example-com", "b.example.com", "web-p80", 80)
    net.read_namespaced_ingress = AsyncMock(return_value=a)
    net.list_namespaced_ingress.return_value = NS(items=[a, b])
    assert client.delete(f"{URL}/web-a-example-com").status_code == 204
    net.delete_namespaced_ingress.assert_awaited_once_with("web-a-example-com", "vm-tenant2")
    mock_k8s_client.core_api.delete_namespaced_service.assert_not_awaited()

    net.list_namespaced_ingress.return_value = NS(items=[b])
    net.read_namespaced_ingress.return_value = b
    assert client.delete(f"{URL}/web-b-example-com").status_code == 204
    mock_k8s_client.core_api.delete_namespaced_service.assert_awaited_once_with("web-p80", "vm-tenant2")


def test_unpublish_refuses_another_vms_ingress(client: TestClient, net: MagicMock) -> None:
    net.read_namespaced_ingress = AsyncMock(return_value=_ingress("x", "foo.org", "other-p80", 80, "other"))
    assert client.delete(f"{URL}/x").status_code == 404
    net.delete_namespaced_ingress.assert_not_awaited()


def test_list_reports_certificate_state(
    client: TestClient, net: MagicMock, mock_k8s_client: MagicMock,
) -> None:
    net.list_namespaced_ingress.return_value = NS(items=[_ingress("web-foo-org", "foo.org", "web-p80", 80)])
    mock_k8s_client.custom_api.get_namespaced_custom_object = AsyncMock(return_value={"status": {
        "conditions": [{"type": "Ready", "status": "False", "reason": "DoesNotExist", "message": "Issuing"}],
    }})
    body = client.get(URL).json()
    assert body["allowed_domains"] == ["example.com", "foo.org"]
    assert body["hosts"] == [{
        "name": "web-foo-org", "host": "foo.org", "port": 80,
        "certificate": "Pending", "message": "Issuing",
    }]
