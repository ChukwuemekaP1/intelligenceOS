import pytest
from httpx import AsyncClient

from app.models.membership import WorkspaceRole


@pytest.mark.asyncio
async def test_create_workspace(client: AsyncClient, auth_headers) -> None:
    headers = await auth_headers(email="creator@example.com")
    response = await client.post(
        "/api/v1/workspaces",
        json={"name": "Engineering Core"},
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Engineering Core"
    assert data["role"] == WorkspaceRole.OWNER.value
    assert "id" in data


@pytest.mark.asyncio
async def test_list_workspaces_isolation(client: AsyncClient, auth_headers) -> None:
    headers1 = await auth_headers(email="user1@example.com")
    headers2 = await auth_headers(email="user2@example.com")

    # User 1 creates 2 workspaces
    await client.post("/api/v1/workspaces", json={"name": "WS 1"}, headers=headers1)
    await client.post("/api/v1/workspaces", json={"name": "WS 2"}, headers=headers1)

    # User 2 creates 1 workspace
    await client.post("/api/v1/workspaces", json={"name": "WS 3"}, headers=headers2)

    # User 1 only sees WS 1 and WS 2
    r1 = await client.get("/api/v1/workspaces", headers=headers1)
    assert r1.status_code == 200
    names1 = [w["name"] for w in r1.json()]
    assert "WS 1" in names1 and "WS 2" in names1
    assert "WS 3" not in names1

    # User 2 only sees WS 3
    r2 = await client.get("/api/v1/workspaces", headers=headers2)
    assert r2.status_code == 200
    names2 = [w["name"] for w in r2.json()]
    assert names2 == ["WS 3"]


@pytest.mark.asyncio
async def test_unauthorized_workspace_access(client: AsyncClient, auth_headers) -> None:
    headers1 = await auth_headers(email="owner@example.com")
    headers2 = await auth_headers(email="stranger@example.com")

    create_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Private WS"}, headers=headers1
    )
    workspace_id = create_resp.json()["id"]

    # Stranger tries to view workspace
    get_resp = await client.get(f"/api/v1/workspaces/{workspace_id}", headers=headers2)
    assert get_resp.status_code == 403
    assert "not a member" in get_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_rbac_add_member_roles(client: AsyncClient, auth_headers, create_user) -> None:
    owner_headers = await auth_headers(email="ws_owner@example.com")
    admin_user = await create_user(email="ws_admin@example.com")
    member_user = await create_user(email="ws_member@example.com")
    external_user = await create_user(email="ws_external@example.com")

    # Owner creates workspace
    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "RBAC Test"}, headers=owner_headers
    )
    ws_id = ws_resp.json()["id"]

    # 1. Owner adds Admin
    add_admin = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": admin_user["email"], "role": WorkspaceRole.ADMIN.value},
        headers=owner_headers,
    )
    assert add_admin.status_code == 201
    assert add_admin.json()["role"] == WorkspaceRole.ADMIN.value

    # Get admin login headers
    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    # 2. Admin adds Member
    add_member = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": member_user["email"], "role": WorkspaceRole.MEMBER.value},
        headers=admin_headers,
    )
    assert add_member.status_code == 201

    # 3. Admin attempts to add another OWNER -> Forbidden (403)
    admin_add_owner = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": external_user["email"], "role": WorkspaceRole.OWNER.value},
        headers=admin_headers,
    )
    assert admin_add_owner.status_code == 403

    # 4. Member attempts to add someone -> Forbidden (403)
    member_login = await client.post(
        "/api/v1/auth/login",
        json={"email": member_user["email"], "password": member_user["password"]},
    )
    member_headers = {"Authorization": f"Bearer {member_login.json()['access_token']}"}

    member_add = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": external_user["email"], "role": WorkspaceRole.MEMBER.value},
        headers=member_headers,
    )
    assert member_add.status_code == 403


@pytest.mark.asyncio
async def test_add_nonexistent_or_duplicate_member(
    client: AsyncClient, auth_headers, create_user
) -> None:
    owner_headers = await auth_headers(email="dup_owner@example.com")
    user = await create_user(email="dup_user@example.com")

    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Dupe Test"}, headers=owner_headers
    )
    ws_id = ws_resp.json()["id"]

    # Nonexistent user
    not_found_resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": "nonexistent@example.com", "role": WorkspaceRole.MEMBER.value},
        headers=owner_headers,
    )
    assert not_found_resp.status_code == 404

    # Add member first time
    add_resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": user["email"], "role": WorkspaceRole.MEMBER.value},
        headers=owner_headers,
    )
    assert add_resp.status_code == 201

    # Add duplicate member -> 409 Conflict
    dup_resp = await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": user["email"], "role": WorkspaceRole.MEMBER.value},
        headers=owner_headers,
    )
    assert dup_resp.status_code == 409


@pytest.mark.asyncio
async def test_update_member_roles(client: AsyncClient, auth_headers, create_user) -> None:
    owner_headers = await auth_headers(email="update_owner@example.com")
    member = await create_user(email="target_member@example.com")

    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Update Role WS"}, headers=owner_headers
    )
    ws_id = ws_resp.json()["id"]
    member_user_id = member["data"]["id"]

    # Add as MEMBER
    await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": member["email"], "role": WorkspaceRole.MEMBER.value},
        headers=owner_headers,
    )

    # Owner promotes MEMBER to ADMIN
    promote_resp = await client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{member_user_id}",
        json={"role": WorkspaceRole.ADMIN.value},
        headers=owner_headers,
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["role"] == WorkspaceRole.ADMIN.value

    # Owner demotes ADMIN back to MEMBER
    demote_resp = await client.patch(
        f"/api/v1/workspaces/{ws_id}/members/{member_user_id}",
        json={"role": WorkspaceRole.MEMBER.value},
        headers=owner_headers,
    )
    assert demote_resp.status_code == 200
    assert demote_resp.json()["role"] == WorkspaceRole.MEMBER.value


@pytest.mark.asyncio
async def test_remove_member_rules(client: AsyncClient, auth_headers, create_user) -> None:
    owner_headers = await auth_headers(email="remove_owner@example.com")
    admin_user = await create_user(email="remove_admin@example.com")
    member_user = await create_user(email="remove_member@example.com")

    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Removal Rules"}, headers=owner_headers
    )
    ws_id = ws_resp.json()["id"]
    admin_id = admin_user["data"]["id"]
    member_id = member_user["data"]["id"]

    # Add admin and member
    await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": admin_user["email"], "role": WorkspaceRole.ADMIN.value},
        headers=owner_headers,
    )
    await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": member_user["email"], "role": WorkspaceRole.MEMBER.value},
        headers=owner_headers,
    )

    admin_login = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user["email"], "password": admin_user["password"]},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    member_login = await client.post(
        "/api/v1/auth/login",
        json={"email": member_user["email"], "password": member_user["password"]},
    )
    member_headers = {"Authorization": f"Bearer {member_login.json()['access_token']}"}

    # 1. Member cannot remove admin -> 403
    m_del = await client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{admin_id}", headers=member_headers
    )
    assert m_del.status_code == 403

    # 2. Admin cannot remove owner -> 403
    owner_info = await client.get("/api/v1/auth/me", headers=owner_headers)
    owner_id = owner_info.json()["id"]
    a_del_owner = await client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{owner_id}", headers=admin_headers
    )
    assert a_del_owner.status_code == 403

    # 3. Admin can remove Member -> 204
    a_del_m = await client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{member_id}", headers=admin_headers
    )
    assert a_del_m.status_code == 204

    # 4. Sole Owner cannot remove themselves -> 400
    o_del_self = await client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{owner_id}", headers=owner_headers
    )
    assert o_del_self.status_code == 400


@pytest.mark.asyncio
async def test_member_self_leave(client: AsyncClient, auth_headers, create_user) -> None:
    owner_headers = await auth_headers(email="leave_owner@example.com")
    member_user = await create_user(email="leaving_member@example.com")
    member_id = member_user["data"]["id"]

    ws_resp = await client.post(
        "/api/v1/workspaces", json={"name": "Leave WS"}, headers=owner_headers
    )
    ws_id = ws_resp.json()["id"]

    await client.post(
        f"/api/v1/workspaces/{ws_id}/members",
        json={"email": member_user["email"], "role": WorkspaceRole.MEMBER.value},
        headers=owner_headers,
    )

    member_login = await client.post(
        "/api/v1/auth/login",
        json={"email": member_user["email"], "password": member_user["password"]},
    )
    member_headers = {"Authorization": f"Bearer {member_login.json()['access_token']}"}

    # Member leaves workspace
    leave_resp = await client.delete(
        f"/api/v1/workspaces/{ws_id}/members/{member_id}", headers=member_headers
    )
    assert leave_resp.status_code == 204

    # Member can no longer access workspace
    access_resp = await client.get(f"/api/v1/workspaces/{ws_id}", headers=member_headers)
    assert access_resp.status_code == 403
