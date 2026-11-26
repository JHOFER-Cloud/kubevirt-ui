"""Per-VM firewall: which other VMs in the namespace may reach this one, on which ports.

Stored as a CiliumNetworkPolicy with only ingressDeny rules, owned by the VM.
Deny rules win over any allow and only take traffic away, so a tenant can't
open anything with it; non-VM pods (tunnel, DNS, ingress) are never denied.
An allowed port is expressed as denying every other port from that source.
"""

import json
import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from kubernetes_asyncio.client import ApiException
from pydantic import BaseModel, Field, field_validator

from app.core.auth import User, require_env_member, require_env_viewer
from app.core.naming import get_display_name

router = APIRouter()
logger = logging.getLogger(__name__)

FIREWALL_LABEL = "kubevirt-ui.io/firewall"
VM_LABEL = "kubevirt-ui.io/vm"
RULES_ANNOTATION = "kubevirt-ui.io/firewall-rules"
VM_NAME_LABEL = "vm.kubevirt.io/name"
MAX_PORT = 65535

CNP = {"group": "cilium.io", "version": "v2", "plural": "ciliumnetworkpolicies"}

_PORTS = re.compile(r"^\d{1,5}(-\d{1,5})?$")

Protocol = Literal["TCP", "UDP", "ANY"]
Range = tuple[int, int]


def parse_ports(spec: str) -> list[Range]:
    """'80, 443, 8000-8100' -> sorted, merged ranges; '' means every port."""
    ranges = []
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        if not _PORTS.match(part):
            raise ValueError(f"'{part}' is not a port or range like 8000-8100")
        lo, _, hi = part.partition("-")
        start, end = int(lo), int(hi or lo)
        if not 1 <= start <= end <= MAX_PORT:
            raise ValueError(f"'{part}' is outside 1-{MAX_PORT}")
        ranges.append((start, end))
    return merge(ranges) if ranges else [(1, MAX_PORT)]


def merge(ranges: list[Range]) -> list[Range]:
    out: list[Range] = []
    for start, end in sorted(ranges):
        if out and start <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def complement(ranges: list[Range]) -> list[Range]:
    out, nxt = [], 1
    for start, end in merge(ranges):
        if start > nxt:
            out.append((nxt, start - 1))
        nxt = end + 1
    if nxt <= MAX_PORT:
        out.append((nxt, MAX_PORT))
    return out


class Rule(BaseModel):
    source: str | None = Field(None, description="VM name; None means any VM in the folder")
    protocol: Protocol = "TCP"
    ports: str = Field("", max_length=200, description="'' for all ports, else '80, 443, 8000-8100'")

    @field_validator("ports")
    @classmethod
    def _valid_ports(cls, v: str) -> str:
        parse_ports(v)
        return v.strip()


class Firewall(BaseModel):
    mode: Literal["all", "rules"]
    rules: list[Rule] = Field(default_factory=list, max_length=50)


class FirewallVM(BaseModel):
    name: str
    display_name: str


class FirewallResponse(Firewall):
    vms: list[FirewallVM]


def policy_name(vm: str) -> str:
    return f"firewall-{vm}"[:63].rstrip("-")


def _allowed(rules: list[Rule]) -> dict[str, list[Range]]:
    allowed: dict[str, list[Range]] = {"TCP": [], "UDP": []}
    for r in rules:
        for proto in (("TCP", "UDP") if r.protocol == "ANY" else (r.protocol,)):
            allowed[proto] += parse_ports(r.ports)
    return allowed


def deny_ports(rules: list[Rule]) -> list[dict] | None:
    """Ports to deny from a source given what it may reach; None denies nothing, [] everything."""
    allowed = _allowed(rules)
    tcp, udp = complement(allowed["TCP"]), complement(allowed["UDP"])
    if not tcp and not udp:
        return None
    if not rules:
        return []
    # Ports denied for both protocols become one ANY entry, the rest stay per protocol.
    both = merge([(max(a, c), min(b, d)) for a, b in tcp for c, d in udp if max(a, c) <= min(b, d)])
    tcp_only = _subtract(tcp, both)
    udp_only = _subtract(udp, both)
    ports = [_port("ANY", r) for r in both] + [_port("TCP", r) for r in tcp_only] + [_port("UDP", r) for r in udp_only]
    return [{"ports": ports}]


def _subtract(ranges: list[Range], minus: list[Range]) -> list[Range]:
    keep = complement(minus)
    return merge([(max(a, c), min(b, d)) for a, b in ranges for c, d in keep if max(a, c) <= min(b, d)])


def _port(protocol: str, r: Range) -> dict:
    entry: dict = {"port": str(r[0]), "protocol": protocol}
    if r[1] != r[0]:
        entry["endPort"] = r[1]
    return entry


def _source(vm_names: list[str] | None, exclude: list[str]) -> dict:
    sel: dict = {"matchLabels": {"kubevirt.io": "virt-launcher"}}
    if vm_names is not None:
        sel["matchExpressions"] = [{"key": VM_NAME_LABEL, "operator": "In", "values": vm_names}]
    else:
        sel["matchExpressions"] = [{"key": VM_NAME_LABEL, "operator": "NotIn", "values": sorted(exclude)}]
    return sel


def build_policy(vm: str, uid: str, fw: Firewall) -> dict:
    any_vm = [r for r in fw.rules if r.source is None]
    named = sorted({r.source for r in fw.rules if r.source and r.source != vm})
    deny = []
    for name in named:
        ports = deny_ports(any_vm + [r for r in fw.rules if r.source == name])
        if ports is not None:
            deny.append({"fromEndpoints": [_source([name], [])], **({"toPorts": ports} if ports else {})})
    ports = deny_ports(any_vm)
    if ports is not None:
        deny.append({"fromEndpoints": [_source(None, [vm, *named])], **({"toPorts": ports} if ports else {})})
    return {
        "apiVersion": "cilium.io/v2",
        "kind": "CiliumNetworkPolicy",
        "metadata": {
            "name": policy_name(vm),
            "labels": {FIREWALL_LABEL: "true", VM_LABEL: vm},
            "annotations": {RULES_ANNOTATION: json.dumps([r.model_dump() for r in fw.rules])},
            "ownerReferences": [{
                "apiVersion": "kubevirt.io/v1", "kind": "VirtualMachine", "name": vm, "uid": uid,
            }],
        },
        "spec": {
            "endpointSelector": {"matchLabels": {VM_NAME_LABEL: vm}},
            # Rules that allow everything still need one rule; this one matches no pod.
            "ingressDeny": deny or [{"fromEndpoints": [{"matchLabels": {FIREWALL_LABEL: "never"}}]}],
        },
    }


def read_policy(policy: dict | None) -> Firewall:
    if policy is None:
        return Firewall(mode="all")
    raw = (policy["metadata"].get("annotations") or {}).get(RULES_ANNOTATION, "[]")
    return Firewall(mode="rules", rules=[Rule(**r) for r in json.loads(raw)])


async def _get_policy(k8s_client, namespace: str, vm: str) -> dict | None:
    try:
        return await k8s_client.custom_api.get_namespaced_custom_object(
            namespace=namespace, name=policy_name(vm), **CNP,
        )
    except ApiException as e:
        if e.status == 404:
            return None
        raise


@router.get("/{name}/firewall", response_model=FirewallResponse)
async def get_firewall(
    request: Request,
    namespace: str,
    name: str,
    user: User = Depends(require_env_viewer()),
) -> FirewallResponse:
    k8s_client = request.app.state.k8s_client
    try:
        policy = await _get_policy(k8s_client, namespace, name)
        vms = await k8s_client.custom_api.list_namespaced_custom_object(
            group="kubevirt.io", version="v1", namespace=namespace, plural="virtualmachines",
        )
    except ApiException as e:
        logger.error(f"Failed to read firewall of {namespace}/{name}: {e}")
        raise HTTPException(status_code=e.status, detail=str(e.reason))

    others = sorted(
        (FirewallVM(name=v["metadata"]["name"], display_name=get_display_name(v["metadata"]) or v["metadata"]["name"])
         for v in vms.get("items", []) if v["metadata"]["name"] != name),
        key=lambda v: v.display_name.lower(),
    )
    fw = read_policy(policy)
    return FirewallResponse(mode=fw.mode, rules=fw.rules, vms=others)


@router.put("/{name}/firewall", response_model=Firewall)
async def set_firewall(
    request: Request,
    namespace: str,
    name: str,
    body: Firewall,
    user: User = Depends(require_env_member()),
) -> Firewall:
    if body.mode == "all":
        body = Firewall(mode="all")
    k8s_client = request.app.state.k8s_client
    api = k8s_client.custom_api
    try:
        existing = await _get_policy(k8s_client, namespace, name)
        if body.mode == "all":
            if existing is not None:
                await api.delete_namespaced_custom_object(namespace=namespace, name=policy_name(name), **CNP)
        else:
            vm = await api.get_namespaced_custom_object(
                group="kubevirt.io", version="v1", namespace=namespace, plural="virtualmachines", name=name,
            )
            policy = build_policy(name, vm["metadata"]["uid"], body)
            if existing is None:
                await api.create_namespaced_custom_object(namespace=namespace, body=policy, **CNP)
            else:
                policy["metadata"]["resourceVersion"] = existing["metadata"]["resourceVersion"]
                await api.replace_namespaced_custom_object(
                    namespace=namespace, name=policy_name(name), body=policy, **CNP,
                )
    except ApiException as e:
        logger.error(f"Failed to set firewall of {namespace}/{name}: {e}")
        raise HTTPException(status_code=e.status, detail=f"Failed to save the firewall: {e.reason}")

    logger.info(f"{user.username} set firewall of {namespace}/{name}: {body.mode} {len(body.rules)} rules")
    return body
