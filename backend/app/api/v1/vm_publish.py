"""Publish a VM port as an HTTPS host.

A host is a ClusterIP Service selecting the VM's launcher pod plus an Ingress,
both owned by the VM so they go with it. Which hosts a namespace may use is set
by the admin in its kubevirt-ui.io/allowed-domains annotation; ingress class,
annotations and certificates are left to the cluster (admission policies).
"""

import logging
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from kubernetes_asyncio import client
from kubernetes_asyncio.client import ApiException
from pydantic import BaseModel, Field

from app.core.auth import User, require_env_member, require_env_viewer
from app.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_DOMAINS_ANNOTATION = "kubevirt-ui.io/allowed-domains"
PUBLISHED_LABEL = "kubevirt-ui.io/published"
VM_LABEL = "kubevirt-ui.io/vm"
PROTOCOL_LABEL = "kubevirt-ui.io/backend-protocol"

_HOST = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class PublishRequest(BaseModel):
    host: str = Field(..., min_length=1, max_length=253)
    port: int = Field(..., ge=1, le=65535)
    protocol: Literal["http", "https"] = "http"


class PublishedHost(BaseModel):
    name: str
    host: str
    port: int
    protocol: str
    certificate: str  # Ready, Pending, Failed or Unknown
    message: str | None = None


class PublishedResponse(BaseModel):
    allowed_domains: list[str]
    dns_target: str
    hosts: list[PublishedHost]


def parse_domains(annotations: dict[str, str] | None) -> list[str]:
    raw = (annotations or {}).get(ALLOWED_DOMAINS_ANNOTATION, "")
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def host_allowed(host: str, domains: list[str]) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def ingress_name(vm: str, host: str) -> str:
    # <name>-tls must stay a valid Secret name, and the admission policy requires it.
    return f"{vm}-{host.replace('.', '-')}"[:240].rstrip("-")


def service_name(vm: str, port: int, protocol: str) -> str:
    suffix = "-https" if protocol == "https" else ""
    return f"{vm[:44].rstrip('-')}-p{port}{suffix}"


async def _allowed_domains(k8s_client, namespace: str) -> list[str]:
    ns = await k8s_client.core_api.read_namespace(namespace)
    return parse_domains(ns.metadata.annotations)


async def _certificate(namespace: str, secret: str, k8s_client) -> tuple[str, str | None]:
    """cert-manager names the Certificate after the Ingress's TLS secret."""
    try:
        cert = await k8s_client.custom_api.get_namespaced_custom_object(
            group="cert-manager.io", version="v1", namespace=namespace,
            plural="certificates", name=secret,
        )
    except ApiException as e:
        return ("Pending", None) if e.status == 404 else ("Unknown", None)
    for cond in cert.get("status", {}).get("conditions", []):
        if cond.get("type") == "Ready":
            if cond.get("status") == "True":
                return "Ready", None
            failed = cond.get("reason") == "Failed"
            return ("Failed" if failed else "Pending"), cond.get("message")
    return "Pending", None


@router.get("/{name}/published", response_model=PublishedResponse)
async def list_published(
    request: Request,
    namespace: str,
    name: str,
    user: User = Depends(require_env_viewer()),
) -> PublishedResponse:
    k8s_client = request.app.state.k8s_client
    net = client.NetworkingV1Api(k8s_client._api_client)
    try:
        domains = await _allowed_domains(k8s_client, namespace)
        ingresses = await net.list_namespaced_ingress(
            namespace, label_selector=f"{PUBLISHED_LABEL}=true,{VM_LABEL}={name}",
        )
    except ApiException as e:
        logger.error(f"Failed to list published hosts: {e}")
        raise HTTPException(status_code=e.status, detail=str(e.reason))

    hosts = []
    for ing in ingresses.items:
        rule = ing.spec.rules[0]
        backend = rule.http.paths[0].backend.service
        secret = ing.spec.tls[0].secret_name if ing.spec.tls else ""
        cert, message = await _certificate(namespace, secret, k8s_client)
        hosts.append(PublishedHost(
            name=ing.metadata.name, host=rule.host, port=backend.port.number,
            protocol=(ing.metadata.labels or {}).get(PROTOCOL_LABEL, "http"),
            certificate=cert, message=message,
        ))
    hosts.sort(key=lambda h: h.host)
    return PublishedResponse(
        allowed_domains=domains, dns_target=get_settings().publish_dns_target, hosts=hosts,
    )


@router.post("/{name}/published", status_code=status.HTTP_201_CREATED, response_model=PublishedHost)
async def publish(
    request: Request,
    namespace: str,
    name: str,
    body: PublishRequest,
    user: User = Depends(require_env_member()),
) -> PublishedHost:
    host = body.host.strip().lower().rstrip(".")
    if not _HOST.match(host):
        raise HTTPException(status_code=422, detail=f"{host} is not a valid hostname")

    k8s_client = request.app.state.k8s_client
    domains = await _allowed_domains(k8s_client, namespace)
    if not host_allowed(host, domains):
        allowed = ", ".join(domains) or "none"
        raise HTTPException(
            status_code=403, detail=f"{host} is not in this folder's allowed domains ({allowed})",
        )

    try:
        vm = await k8s_client.custom_api.get_namespaced_custom_object(
            group="kubevirt.io", version="v1", namespace=namespace,
            plural="virtualmachines", name=name,
        )
    except ApiException as e:
        raise HTTPException(status_code=e.status, detail=f"VM {name}: {e.reason}")

    owner = {
        "apiVersion": "kubevirt.io/v1", "kind": "VirtualMachine",
        "name": name, "uid": vm["metadata"]["uid"],
    }
    # The cluster turns the protocol label into the ingress controller's backend settings.
    labels = {PUBLISHED_LABEL: "true", VM_LABEL: name, PROTOCOL_LABEL: body.protocol}
    svc_name = service_name(name, body.port, body.protocol)
    ing_name = ingress_name(name, host)

    service = {
        "apiVersion": "v1", "kind": "Service",
        "metadata": {"name": svc_name, "labels": labels, "ownerReferences": [owner]},
        "spec": {
            "selector": {"vm.kubevirt.io/name": name},
            "ports": [{"name": body.protocol, "port": body.port, "targetPort": body.port}],
        },
    }
    ingress = {
        "apiVersion": "networking.k8s.io/v1", "kind": "Ingress",
        "metadata": {"name": ing_name, "labels": labels, "ownerReferences": [owner]},
        "spec": {
            "tls": [{"hosts": [host], "secretName": f"{ing_name}-tls"}],
            "rules": [{
                "host": host,
                "http": {"paths": [{
                    "path": "/", "pathType": "Prefix",
                    "backend": {"service": {"name": svc_name, "port": {"number": body.port}}},
                }]},
            }],
        },
    }

    net = client.NetworkingV1Api(k8s_client._api_client)
    try:
        existing = await net.list_namespaced_ingress(namespace, label_selector=f"{PUBLISHED_LABEL}=true")
        if any(r.host == host for i in existing.items for r in i.spec.rules or []):
            raise HTTPException(status_code=409, detail=f"{host} is already published")
        try:
            await k8s_client.core_api.create_namespaced_service(namespace, service)
        except ApiException as e:
            if e.status != 409:  # another host on the same port shares it
                raise
        await net.create_namespaced_ingress(namespace, ingress)
    except ApiException as e:
        logger.error(f"Failed to publish {host}: {e}")
        raise HTTPException(status_code=e.status, detail=f"Failed to publish {host}: {e.reason}")

    logger.info(f"{user.username} published {namespace}/{name}:{body.port} ({body.protocol}) as {host}")
    return PublishedHost(
        name=ing_name, host=host, port=body.port, protocol=body.protocol, certificate="Pending",
    )


@router.delete("/{name}/published/{ingress}", status_code=status.HTTP_204_NO_CONTENT)
async def unpublish(
    request: Request,
    namespace: str,
    name: str,
    ingress: str,
    user: User = Depends(require_env_member()),
) -> None:
    k8s_client = request.app.state.k8s_client
    net = client.NetworkingV1Api(k8s_client._api_client)
    try:
        ing = await net.read_namespaced_ingress(ingress, namespace)
        if (ing.metadata.labels or {}).get(VM_LABEL) != name:
            raise HTTPException(status_code=404, detail=f"{ingress} is not published for {name}")
        svc = ing.spec.rules[0].http.paths[0].backend.service.name
        await net.delete_namespaced_ingress(ingress, namespace)

        rest = await net.list_namespaced_ingress(namespace, label_selector=f"{VM_LABEL}={name}")
        still_used = any(
            p.backend.service and p.backend.service.name == svc
            for i in rest.items if i.metadata.name != ingress
            for r in i.spec.rules or [] for p in (r.http.paths if r.http else [])
        )
        if not still_used:
            try:
                await k8s_client.core_api.delete_namespaced_service(svc, namespace)
            except ApiException as e:
                if e.status != 404:
                    raise
    except ApiException as e:
        logger.error(f"Failed to unpublish {ingress}: {e}")
        raise HTTPException(status_code=e.status, detail=str(e.reason))
    logger.info(f"{user.username} unpublished {namespace}/{ingress}")
