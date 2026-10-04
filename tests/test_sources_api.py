"""Tests for Sources API endpoints and Workspace Authorization."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.core.config import Settings
from app.queue.job_queue import get_job_queue
from app.storage.factory import get_storage_backend


@pytest_asyncio.fixture(autouse=True)
async def setup_test_services() -> AsyncGenerator[None, None]:
    """Configures mock storage and mock queue for API test runs."""
    test_settings = Settings(
        STORAGE_BACKEND="mock",
        ENVIRONMENT="testing",
        EMBEDDING_PROVIDER="mock",
    )
    get_storage_backend(test_settings)
    get_job_queue(test_settings)
    yield


@pytest.mark.asyncio
async def test_upload_file_source_success(
    client: AsyncClient,
    auth_headers: Any,
) -> None:
    """Verifies that an authorized user can upload a file, returning 202 Accepted."""
    headers = await auth_headers("uploader@example.com", "securepassword123")

    # 1. Create a workspace
    ws_resp = await client.post(
        "/api/v1/workspaces",
        json={"name": "Knowledge Vault"},
        headers=headers,
    )
    assert ws_resp.status_code == 201
    workspace_id = ws_resp.json()["id"]

    # 2. Upload a CSV file
    csv_file = ("data.csv", b"col1,col2\nval1,val2\n", "text/csv")
    upload_resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sources/upload",
        files={"file": csv_file},
        headers=headers,
    )
    assert upload_resp.status_code == 202, upload_resp.text
    data = upload_resp.json()
    assert data["name"] == "data.csv"
    assert data["source_type"] == "csv"
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_upload_unsupported_file_type(
    client: AsyncClient,
    auth_headers: Any,
) -> None:
    """Verifies that uploading an unsupported executable or file type returns 400 Bad Request."""
    headers = await auth_headers("uploader2@example.com", "securepassword123")
    ws_resp = await client.post("/api/v1/workspaces", json={"name": "Test WS"}, headers=headers)
    workspace_id = ws_resp.json()["id"]

    exe_file = ("malware.exe", b"MZ\x90\x00BinaryContent", "application/x-msdownload")
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sources/upload",
        files={"file": exe_file},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_submit_url_source_ssrf_blocked(
    client: AsyncClient,
    auth_headers: Any,
) -> None:
    """Verifies that submitting private or loopback URLs returns 400 Bad Request."""
    headers = await auth_headers("uploader3@example.com", "securepassword123")
    ws_resp = await client.post("/api/v1/workspaces", json={"name": "Test WS"}, headers=headers)
    workspace_id = ws_resp.json()["id"]

    # Attempt loopback SSRF
    resp = await client.post(
        f"/api/v1/workspaces/{workspace_id}/sources/url",
        json={"url": "http://127.0.0.1:8000/internal"},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "validation failed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_list_and_get_source_details(
    client: AsyncClient,
    auth_headers: Any,
) -> None:
    """Verifies listing sources and retrieving details by source ID."""
    headers = await auth_headers("owner@example.com", "securepassword123")
    ws_resp = await client.post("/api/v1/workspaces", json={"name": "List WS"}, headers=headers)
    workspace_id = ws_resp.json()["id"]

    # Upload 2 sources
    for name in ("file1.csv", "file2.csv"):
        await client.post(
            f"/api/v1/workspaces/{workspace_id}/sources/upload",
            files={"file": (name, b"a,b\n1,2\n", "text/csv")},
            headers=headers,
        )

    # List sources
    list_resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/sources",
        headers=headers,
    )
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 2
    first_id = items[0]["id"]

    # Get single source details
    detail_resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/sources/{first_id}",
        headers=headers,
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == first_id

    # Get documents
    docs_resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/sources/{first_id}/documents",
        headers=headers,
    )
    assert docs_resp.status_code == 200
    assert len(docs_resp.json()) == 1

    # Get chunks
    chunks_resp = await client.get(
        f"/api/v1/workspaces/{workspace_id}/sources/{first_id}/chunks",
        headers=headers,
    )
    assert chunks_resp.status_code == 200


@pytest.mark.asyncio
async def test_workspace_isolation_on_sources(
    client: AsyncClient,
    auth_headers: Any,
) -> None:
    """Verifies that User B cannot view or access sources belonging to User A's workspace."""
    headers_a = await auth_headers("tenant_a@example.com", "securepassword123")
    headers_b = await auth_headers("tenant_b@example.com", "securepassword123")

    # Tenant A creates workspace and source
    ws_a_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Tenant A Vault"}, headers=headers_a
    )
    ws_a_id = ws_a_resp.json()["id"]

    upload_resp = await client.post(
        f"/api/v1/workspaces/{ws_a_id}/sources/upload",
        files={"file": ("secret.csv", b"confidential,data\n1,2\n", "text/csv")},
        headers=headers_a,
    )
    source_a_id = upload_resp.json()["id"]

    # Tenant B creates their own workspace
    ws_b_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Tenant B Vault"}, headers=headers_b
    )
    ws_b_id = ws_b_resp.json()["id"]

    # 1. Tenant B tries to list sources from Tenant A's workspace -> 403 Forbidden
    list_attempt = await client.get(
        f"/api/v1/workspaces/{ws_a_id}/sources",
        headers=headers_b,
    )
    assert list_attempt.status_code == 403

    # 2. Tenant B tries to access Tenant A's source_id using Tenant B's
    # workspace path -> 404 Not Found
    get_attempt = await client.get(
        f"/api/v1/workspaces/{ws_b_id}/sources/{source_a_id}",
        headers=headers_b,
    )
    assert get_attempt.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_sources_access(
    client: AsyncClient,
) -> None:
    """Verifies that unauthenticated requests receive 401 Unauthorized."""
    random_ws = uuid.uuid4()
    resp = await client.get(f"/api/v1/workspaces/{random_ws}/sources")
    assert resp.status_code == 401
