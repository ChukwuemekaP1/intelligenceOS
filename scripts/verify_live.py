import httpx

client = httpx.Client(base_url="http://localhost:8000")

print("--- 1. Testing Health and Readiness ---")
hz = client.get("/healthz")
assert hz.status_code == 200, f"Healthz failed: {hz.text}"
print("[PASS] Healthz:", hz.json())

rz = client.get("/readyz")
assert rz.status_code == 200, f"Readyz failed: {rz.text}"
print("[PASS] Readyz:", rz.json())

print("\n--- 2. Testing Registration ---")
r1 = client.post(
    "/api/v1/auth/register",
    json={"email": "alice@corp.com", "password": "StrongPassword123!"},
)
assert r1.status_code == 201, f"Alice registration failed: {r1.text}"
print(f"[PASS] Registered Alice: {r1.json()['email']} (ID: {r1.json()['id']})")

r2 = client.post(
    "/api/v1/auth/register",
    json={"email": "bob@corp.com", "password": "StrongPassword123!"},
)
assert r2.status_code == 201, f"Bob registration failed: {r2.text}"
print(f"[PASS] Registered Bob: {r2.json()['email']} (ID: {r2.json()['id']})")

# Duplicate registration check
r_dup = client.post(
    "/api/v1/auth/register",
    json={"email": "alice@corp.com", "password": "StrongPassword123!"},
)
assert r_dup.status_code == 409, f"Expected 409 Conflict for duplicate: {r_dup.text}"
print("[PASS] Duplicate registration rejected with 409 Conflict")

print("\n--- 3. Testing Authentication & Token Issuance ---")
l_bad = client.post(
    "/api/v1/auth/login",
    json={"email": "alice@corp.com", "password": "wrongpassword"},
)
assert l_bad.status_code == 401, f"Expected 401: {l_bad.text}"
print("[PASS] Invalid password rejected with 401 Unauthorized")

l_good = client.post(
    "/api/v1/auth/login",
    json={"email": "alice@corp.com", "password": "StrongPassword123!"},
)
assert l_good.status_code == 200, f"Login failed: {l_good.text}"
alice_token = l_good.json()["access_token"]
print("[PASS] Alice login successful, JWT access token acquired")

print("\n--- 4. Testing Authenticated User Info & Auth Enforcement ---")
unauth = client.get("/api/v1/auth/me")
assert unauth.status_code == 401, f"Expected 401 without token: {unauth.text}"
print("[PASS] Unauthenticated request rejected with 401 Unauthorized")

auth_me = client.get(
    "/api/v1/auth/me",
    headers={"Authorization": f"Bearer {alice_token}"},
)
assert auth_me.status_code == 200 and auth_me.json()["email"] == "alice@corp.com"
print(f"[PASS] Retrieved authenticated profile for: {auth_me.json()['email']}")

print("\n--- 5. Testing Workspace Creation & Multi-tenancy ---")
ws_resp = client.post(
    "/api/v1/workspaces",
    json={"name": "IntelligenceOS Core Workspace"},
    headers={"Authorization": f"Bearer {alice_token}"},
)
assert ws_resp.status_code == 201, f"Create workspace failed: {ws_resp.text}"
ws_data = ws_resp.json()
assert ws_data["role"] == "OWNER"
ws_id = ws_data["id"]
print(f"[PASS] Alice created workspace: '{ws_data['name']}' as OWNER (ID: {ws_id})")

print("\n--- 6. Testing Workspace RBAC (OWNER / MEMBER roles) ---")
# Alice adds Bob as MEMBER
add_bob = client.post(
    f"/api/v1/workspaces/{ws_id}/members",
    json={"email": "bob@corp.com", "role": "MEMBER"},
    headers={"Authorization": f"Bearer {alice_token}"},
)
assert add_bob.status_code == 201 and add_bob.json()["role"] == "MEMBER"
print(f"[PASS] Alice added Bob as MEMBER: {add_bob.json()['email']}")

# Bob logs in
bob_login = client.post(
    "/api/v1/auth/login",
    json={"email": "bob@corp.com", "password": "StrongPassword123!"},
)
bob_token = bob_login.json()["access_token"]

# Bob tries to add another user -> Forbidden (403)
bob_add_illegal = client.post(
    f"/api/v1/workspaces/{ws_id}/members",
    json={"email": "charlie@corp.com", "role": "MEMBER"},
    headers={"Authorization": f"Bearer {bob_token}"},
)
assert bob_add_illegal.status_code == 403, f"Expected 403: {bob_add_illegal.text}"
print("[PASS] Bob (MEMBER) attempting to invite members correctly rejected with 403 Forbidden")

# Bob lists workspaces -> sees Core Workspace as MEMBER
bob_workspaces = client.get(
    "/api/v1/workspaces",
    headers={"Authorization": f"Bearer {bob_token}"},
)
assert bob_workspaces.status_code == 200
assert any(w["id"] == ws_id and w["role"] == "MEMBER" for w in bob_workspaces.json())
print("[PASS] Bob lists workspaces and sees membership role as MEMBER")

# List members in workspace
members_list = client.get(
    f"/api/v1/workspaces/{ws_id}/members",
    headers={"Authorization": f"Bearer {bob_token}"},
)
assert members_list.status_code == 200
emails = [m["email"] for m in members_list.json()]
assert "alice@corp.com" in emails and "bob@corp.com" in emails
print(f"[PASS] Workspace member list verified: {emails}")

print("\n=======================================================")
print("ALL LIVE VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
print("=======================================================")
