"""Images in SHARED_IMAGE_NAMESPACES are usable from every namespace.

Without them, one image for everybody meant one clone of it per tenant
namespace (each counted against that tenant's storage quota) and one template
per tenant pointing at that clone.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kubernetes_asyncio.client import ApiException

from app.api.v1 import images, vms
from app.config import Settings
from app.core.auth import User

MINE = "tenant-mine"
SHARED = "vm-images"


def _user() -> User:
    return User(id="u", email="u@example.test", username="u", groups=["team-mine"])


def _k8s() -> MagicMock:
    k8s = MagicMock()
    k8s.list_namespaces = AsyncMock(return_value=[
        {"name": MINE, "status": "Active", "labels": {"kubevirt-ui.io/enabled": "true"}},
    ])
    k8s.core_api.read_namespace = AsyncMock(return_value=SimpleNamespace(
        metadata=SimpleNamespace(labels={}),
    ))
    return k8s


def _mine_only():
    return patch(
        "kubernetes_asyncio.client.RbacAuthorizationV1Api",
        return_value=SimpleNamespace(list_namespaced_role_binding=AsyncMock(
            side_effect=lambda namespace, **_: SimpleNamespace(items=[
                SimpleNamespace(subjects=[SimpleNamespace(kind="Group", name="team-mine")])
            ] if namespace == MINE else []),
        )),
    )


def _shared(*namespaces: str):
    return patch.object(
        images, "get_settings",
        return_value=Settings(shared_image_namespaces=",".join(namespaces)),
    )


def _dv(name: str, namespace: str, labels: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "metadata": {"name": name, "namespace": namespace, "labels": labels or {}},
        "spec": {"source": {"http": {"url": "https://example.test/x.qcow2"}}},
        "status": {"phase": "Succeeded"},
    }


CLUSTER: dict[tuple[str, str], list[dict[str, Any]]] = {
    (MINE, "datavolumes"): [_dv("own-image", MINE)],
    (SHARED, "datavolumes"): [
        _dv("debian-13", SHARED),
        _dv("nixos-5e6cc80ca174", SHARED, {"cdi.kubevirt.io/dataImportCron": "nixos"}),
    ],
    (SHARED, "datasources"): [{
        "metadata": {"name": "nixos", "namespace": SHARED},
        "status": {"conditions": [{"type": "Ready", "status": "True"}]},
    }],
}


async def _list(**kwargs: Any) -> dict[str, Any]:
    if kwargs.get("label_selector"):  # the VM-disk scan
        return {"items": []}
    return {"items": CLUSTER.get((kwargs["namespace"], kwargs["plural"]), [])}


async def _images(namespace: str | None = None, shared: tuple[str, ...] = (SHARED,)):
    request = MagicMock()
    request.app.state.k8s_client = _k8s()
    api = MagicMock()
    api.list_namespaced_custom_object = AsyncMock(side_effect=_list)
    with _mine_only(), _shared(*shared), patch.object(
        images.client, "CustomObjectsApi", return_value=api,
    ):
        got = await images.list_golden_images(request=request, user=_user(), namespace=namespace)
    return {(i.namespace, i.name): i.shared for i in got.items}


@pytest.mark.asyncio
class TestTheImageList:
    @pytest.mark.parametrize("namespace", [None, MINE])
    async def test_shared_images_are_listed_next_to_your_own(self, namespace: str | None) -> None:
        assert await _images(namespace) == {
            (MINE, "own-image"): False,
            (SHARED, "debian-13"): True,
            (SHARED, "nixos"): True,
        }

    async def test_a_data_import_crons_versioned_volume_is_not_listed(self) -> None:
        """Its name changes with every import; the DataSource is the stable one."""
        assert (SHARED, "nixos-5e6cc80ca174") not in await _images()

    async def test_nothing_is_shared_unless_configured(self) -> None:
        assert await _images(shared=()) == {(MINE, "own-image"): False}


@pytest.mark.asyncio
class TestTheCloneSource:
    async def test_a_data_source_is_cloned_by_reference(self) -> None:
        api = MagicMock()
        api.get_namespaced_custom_object = AsyncMock(return_value={})
        assert await vms._clone_source(api, SHARED, "nixos") == {
            "sourceRef": {"kind": "DataSource", "name": "nixos", "namespace": SHARED},
        }

    async def test_anything_else_is_cloned_as_a_pvc(self) -> None:
        api = MagicMock()
        api.get_namespaced_custom_object = AsyncMock(side_effect=ApiException(status=404))
        assert await vms._clone_source(api, SHARED, "debian-13") == {
            "source": {"pvc": {"name": "debian-13", "namespace": SHARED}},
        }

    async def test_a_failed_lookup_is_not_mistaken_for_a_pvc(self) -> None:
        api = MagicMock()
        api.get_namespaced_custom_object = AsyncMock(side_effect=ApiException(status=403))
        with pytest.raises(ApiException):
            await vms._clone_source(api, SHARED, "nixos")
