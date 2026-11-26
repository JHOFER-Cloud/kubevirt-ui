"""A VM's firewall is a deny-only CiliumNetworkPolicy: allowed ports become denies of every other port."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from kubernetes_asyncio.client import ApiException

from app.api.v1.vm_firewall import Firewall, Rule, build_policy, complement, parse_ports, read_policy

URL = "/api/v1/namespaces/vm-tenant2/vms/db/firewall"


def _deny(*rules: dict) -> list[dict]:
    fw = Firewall(mode="rules", rules=[Rule(**r) for r in rules])
    return build_policy("db", "uid", fw)["spec"]["ingressDeny"]


def _ports(rule: dict) -> set[tuple]:
    return {(p["protocol"], int(p["port"]), p.get("endPort", int(p["port"]))) for p in rule["toPorts"][0]["ports"]}


@pytest.fixture
def api(mock_k8s_client: MagicMock) -> MagicMock:
    custom = mock_k8s_client.custom_api

    async def get(**kw):
        if kw.get("plural") == "virtualmachines":
            return {"metadata": {"uid": "db-uid"}}
        raise ApiException(status=404)

    custom.get_namespaced_custom_object = AsyncMock(side_effect=get)
    custom.list_namespaced_custom_object = AsyncMock(return_value={"items": [
        {"metadata": {"name": "db"}}, {"metadata": {"name": "web"}}, {"metadata": {"name": "app"}},
    ]})
    custom.create_namespaced_custom_object = AsyncMock()
    custom.replace_namespaced_custom_object = AsyncMock()
    custom.delete_namespaced_custom_object = AsyncMock()
    return custom


def test_ports_parse_merge_and_complement() -> None:
    assert parse_ports("443, 80,81, 8000-8100") == [(80, 81), (443, 443), (8000, 8100)]
    assert parse_ports("") == [(1, 65535)]
    assert complement([(1, 79), (81, 65535)]) == [(80, 80)]
    for bad in ("0", "70000", "90-80", "http"):
        with pytest.raises(ValueError):
            parse_ports(bad)


def test_one_vm_on_one_port_denies_it_everything_else_and_other_vms_all() -> None:
    web, rest = _deny({"source": "web", "protocol": "TCP", "ports": "5432"})
    assert web["fromEndpoints"][0]["matchExpressions"][0] == {
        "key": "vm.kubevirt.io/name", "operator": "In", "values": ["web"],
    }
    assert _ports(web) == {("ANY", 1, 5431), ("ANY", 5433, 65535), ("UDP", 5432, 5432)}
    assert rest["fromEndpoints"][0]["matchExpressions"][0]["values"] == ["db", "web"]
    assert "toPorts" not in rest


def test_rules_for_any_vm_also_apply_to_named_vms() -> None:
    web, rest = _deny(
        {"source": None, "protocol": "TCP", "ports": "80"},
        {"source": "web", "protocol": "TCP", "ports": "5432"},
    )
    assert ("TCP", 80, 80) not in _ports(web) and ("ANY", 81, 5431) in _ports(web)
    assert _ports(rest) == {("ANY", 1, 79), ("ANY", 81, 65535), ("UDP", 80, 80)}


def test_no_rules_denies_every_other_vm() -> None:
    (rest,) = _deny()
    assert "toPorts" not in rest
    assert rest["fromEndpoints"][0]["matchLabels"] == {"kubevirt.io": "virt-launcher"}


def test_allowing_everything_denies_nothing() -> None:
    (rule,) = _deny({"source": None, "protocol": "ANY", "ports": ""})
    assert rule == {"fromEndpoints": [{"matchLabels": {"kubevirt-ui.io/firewall": "never"}}]}


def test_policy_only_has_deny_rules_and_round_trips() -> None:
    fw = Firewall(mode="rules", rules=[Rule(source="web", protocol="UDP", ports="53")])
    policy = build_policy("db", "uid", fw)
    assert set(policy["spec"]) == {"endpointSelector", "ingressDeny"}
    assert policy["metadata"]["labels"]["kubevirt-ui.io/firewall"] == "true"
    assert read_policy(policy) == fw
    assert read_policy(None) == Firewall(mode="all")


def test_get_lists_the_other_vms(client: TestClient, api: MagicMock) -> None:
    body = client.get(URL).json()
    assert body["mode"] == "all"
    assert [v["name"] for v in body["vms"]] == ["app", "web"]


def test_saving_rules_creates_the_policy(client: TestClient, api: MagicMock) -> None:
    r = client.put(URL, json={"mode": "rules", "rules": [{"source": "web", "protocol": "TCP", "ports": "5432"}]})
    assert r.status_code == 200, r.text
    assert api.create_namespaced_custom_object.await_args.kwargs["body"]["metadata"]["name"] == "firewall-db"


def test_invalid_ports_are_refused(client: TestClient, api: MagicMock) -> None:
    r = client.put(URL, json={"mode": "rules", "rules": [{"source": None, "protocol": "TCP", "ports": "80-"}]})
    assert r.status_code == 422
    api.create_namespaced_custom_object.assert_not_awaited()


def test_back_to_all_deletes_the_policy(client: TestClient, api: MagicMock) -> None:
    api.get_namespaced_custom_object.side_effect = None
    api.get_namespaced_custom_object.return_value = build_policy("db", "uid", Firewall(mode="rules"))
    assert client.put(URL, json={"mode": "all", "rules": [{"ports": "22"}]}).json() == {"mode": "all", "rules": []}
    api.delete_namespaced_custom_object.assert_awaited_once()


def test_changing_an_existing_firewall_replaces_it(client: TestClient, api: MagicMock) -> None:
    existing = build_policy("db", "uid", Firewall(mode="rules"))
    existing["metadata"]["resourceVersion"] = "7"

    async def get(**kw):
        return {"metadata": {"uid": "db-uid"}} if kw.get("plural") == "virtualmachines" else existing

    api.get_namespaced_custom_object.side_effect = get
    assert client.put(URL, json={"mode": "rules", "rules": [{"source": "app", "ports": ""}]}).status_code == 200
    assert api.replace_namespaced_custom_object.await_args.kwargs["body"]["metadata"]["resourceVersion"] == "7"
