"""User documentation pages.

Pages are Markdown, one per key of every ConfigMap in the system namespace
labelled kubevirt-ui.io/docs=true, so each deployment ships its own docs
without a UI build. Pages sort by key, so a numeric prefix (10-ssh.md) orders
them; the title is the page's first level-1 heading.
"""

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from kubernetes_asyncio.client.rest import ApiException
from pydantic import BaseModel

from app.core.constants import SYSTEM_NAMESPACE

logger = logging.getLogger(__name__)
router = APIRouter()

DOCS_LABEL = "kubevirt-ui.io/docs=true"

_ORDER_PREFIX = re.compile(r"^\d+[-_]")
_H1 = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)


class DocPage(BaseModel):
    slug: str
    title: str
    content: str


class DocsResponse(BaseModel):
    pages: list[DocPage]


def _slug(key: str) -> str:
    return _ORDER_PREFIX.sub("", key.removesuffix(".md"))


def _title(slug: str, content: str) -> str:
    match = _H1.search(content)
    return match.group(1) if match else slug.replace("-", " ").replace("_", " ").capitalize()


def build_pages(configmaps: list) -> list[DocPage]:
    entries = sorted(
        (key, content)
        for cm in configmaps
        for key, content in (cm.data or {}).items()
    )
    pages: dict[str, DocPage] = {}
    for key, content in entries:
        slug = _slug(key)
        if slug in pages:
            logger.warning("Docs page %s is defined twice, keeping the first", slug)
            continue
        pages[slug] = DocPage(slug=slug, title=_title(slug, content), content=content)
    return list(pages.values())


@router.get("", response_model=DocsResponse)
async def list_docs(request: Request) -> DocsResponse:
    k8s_client = request.app.state.k8s_client
    try:
        result = await k8s_client.core_api.list_namespaced_config_map(
            namespace=SYSTEM_NAMESPACE, label_selector=DOCS_LABEL,
        )
    except ApiException as e:
        logger.error(f"Failed to list docs ConfigMaps: {e}")
        raise HTTPException(status_code=e.status, detail=str(e.reason))
    return DocsResponse(pages=build_pages(result.items))
