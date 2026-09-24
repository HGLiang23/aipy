"""Live smoke test: exercise every admin API over real HTTP.

    .venv\\Scripts\\python.exe scripts/smoke_admin.py [BASE_URL]

Default BASE_URL is ``http://127.0.0.1:8000`` (the API directly). Pass
``http://127.0.0.1:3000`` to test through the Next.js dev proxy instead.

Why this exists: in-process ``TestClient`` tests cannot catch a stale running
server, a broken dev proxy, or a route that was never registered. This script
talks to a real socket so those failures surface immediately.

Write checks create data with a ``__smoke__`` prefix and cannot remove it over
HTTP (members are suspended, never purged; credentials are revoked). Run
``scripts/cleanup_smoke_data.py`` afterwards to purge the leftovers.

Exit code is non-zero when any check fails.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
EMAIL = "editor@example.com"
PASSWORD = "demo-password"

_opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    urllib.request.HTTPCookieProcessor(CookieJar()),
)

failures: list[str] = []
checks = 0


def call(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with _opener.open(req, timeout=20) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw) if raw else None
            except json.JSONDecodeError:
                return resp.status, raw[:200].decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, raw[:200].decode("utf-8", "replace")


def check(name: str, ok: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if ok:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        failures.append(name)


def login(email: str, password: str) -> int:
    """Log in on a throwaway cookie jar and return the status code.

    Uses its own jar so probing one member's credentials never disturbs the
    authenticated session the rest of the script relies on.
    """

    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(CookieJar()),
    )
    req = urllib.request.Request(
        f"{BASE}/api/v1/auth/login",
        data=json.dumps({"email": email, "password": password}).encode(),
        method="POST",
    )
    req.add_header("Content-Type", "application/json")
    try:
        with opener.open(req, timeout=20) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def main() -> int:
    print(f"Smoke target: {BASE}\n")

    # ── Auth ──────────────────────────────────────────────────────────
    status, session = call("POST", "/api/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    check("POST /auth/login", status == 200, f"-> {status} {session if status != 200 else ''}")
    if status != 200:
        print("\nCannot continue without a session.")
        return 1
    permissions = set(session.get("permissions", []))
    check(
        "login grants admin permissions",
        "role:manage" in permissions and "quota:configure" in permissions,
    )

    # ── Read endpoints ────────────────────────────────────────────────
    expected_min: dict[str, int] = {
        "/api/v1/roles": 1,
        "/api/v1/members": 1,
        "/api/v1/workflow-templates": 1,
        "/api/v1/model-credentials": 0,
        "/api/v1/quotas": 1,
        "/api/v1/audit-logs": 0,
        "/api/v1/model-routing-policies": 0,
    }
    read_data: dict[str, object] = {}
    for path, minimum in expected_min.items():
        status, payload = call("GET", path)
        count = -1
        if status == 200 and isinstance(payload, (list, dict)):
            if isinstance(payload, dict):
                count = len(payload.get("items", payload))
            else:
                count = len(payload)
        read_data[path] = payload
        check(f"GET {path}", status == 200 and count >= minimum, f"-> {status}, {count} rows")

    status, overview = call("GET", "/api/v1/quotas/overview")
    check("GET /quotas/overview", status == 200 and isinstance(overview, dict), f"-> {status}")

    # ── Write endpoints (each reverted to its original value) ─────────
    roles = read_data.get("/api/v1/roles") or []
    if isinstance(roles, list) and len(roles) >= 2:
        target, other = roles[0], roles[1]

        status, _ = call("PUT", f"/api/v1/roles/{other['id']}", {"description": "冒烟测试"})
        check("PUT /roles/{id}", status == 200, f"-> {status}")

        status, _ = call("PUT", f"/api/v1/roles/{target['id']}", {"name": other["name"]})
        check("PUT /roles/{id} duplicate name -> 409", status == 409, f"-> {status}")

        status, detail = call("GET", f"/api/v1/roles/{target['id']}")
        check(
            "GET /roles/{id} reports memberCount",
            status == 200 and isinstance(detail, dict) and "memberCount" in detail,
            f"-> {status}",
        )

    status, policy = call(
        "PUT", "/api/v1/quotas/AI_COST",
        {"period_type": "MONTHLY", "soft_limit": 2000, "hard_limit": 4000,
         "overage_allowed": False, "status": "ACTIVE"},
    )
    check("PUT /quotas/{metric}", status == 200, f"-> {status}")

    status, _ = call(
        "PUT", "/api/v1/quotas/AI_COST",
        {"period_type": "MONTHLY", "soft_limit": 9000, "hard_limit": 10,
         "overage_allowed": False, "status": "ACTIVE"},
    )
    check("PUT /quotas/{metric} soft>hard -> 422", status == 422, f"-> {status}")

    status, _ = call(
        "PUT", "/api/v1/model-routing-policies/__SMOKE__",
        {"name": "冒烟策略", "daily_cost_limit": None, "per_call_timeout_seconds": 60,
         "status": "DISABLED", "candidates": []},
    )
    check("PUT /model-routing-policies/{type}", status == 200, f"-> {status}")

    providers = call("GET", "/api/v1/model-providers")[1]
    if isinstance(providers, list) and providers:
        # DELETE revokes rather than purges, so a fixed name would collide on the next
        # run. Use a unique name and revoke it at the end.
        marker = f"__smoke__{int(time.time())}"
        status, created = call(
            "POST", "/api/v1/model-credentials",
            {"provider_id": providers[0]["id"], "name": marker, "ownership_type": "BYOK",
             "secret": "sk-smoke-000000000000"},
        )
        check("POST /model-credentials", status == 201, f"-> {status}")
        created_id = created["id"] if status == 201 and isinstance(created, dict) else None

        status, _ = call(
            "POST", "/api/v1/model-credentials",
            {"provider_id": providers[0]["id"], "name": marker, "ownership_type": "BYOK",
             "secret": "sk-smoke-000000000000"},
        )
        check("POST /model-credentials duplicate -> 409", status == 409, f"-> {status}")

        if created_id:
            # Test before revoking: the endpoint rejects REVOKED credentials.
            status, _ = call("POST", f"/api/v1/model-credentials/{created_id}/test")
            check("POST /model-credentials/{id}/test", status == 200, f"-> {status}")

            status, _ = call("DELETE", f"/api/v1/model-credentials/{created_id}")
            check("DELETE /model-credentials/{id}", status == 204, f"-> {status}")

    # ── Members: create is the only way in, and it mints a password ────
    members = read_data.get("/api/v1/members")
    if isinstance(members, dict) and members.get("items"):
        existing = members["items"][0]
        status, _ = call(
            "PUT", f"/api/v1/members/{existing['id']}",
            {"role_id": existing.get("roleId"), "status": existing["status"]},
        )
        check("PUT /members/{id}", status == 200, f"-> {status}")

    role_pool = read_data.get("/api/v1/roles")
    role_pool = role_pool.get("items", []) if isinstance(role_pool, dict) else (role_pool or [])
    viewer = next((r for r in role_pool if r.get("code") == "viewer"), None)
    if viewer:
        marker_email = f"__smoke__{int(time.time())}@example.com"
        status, created = call(
            "POST", "/api/v1/members",
            {"email": marker_email, "displayName": "__smoke__ 冒烟成员",
             "role_id": viewer["id"], "job_title": "冒烟"},
        )
        check("POST /members", status == 201, f"-> {status}")
        member_id = created.get("id") if isinstance(created, dict) else None
        initial_password = created.get("initialPassword") if isinstance(created, dict) else None
        check(
            "POST /members returns a one-time password",
            bool(initial_password) and len(initial_password) >= 12,
            f"-> {status}",
        )

        # The whole point of the feature: the handed-out password must actually work.
        check(
            "generated password can log in",
            login(marker_email, initial_password) == 200,
        )

        # ── Password reset: rotation must actually kill the old credential ──
        if member_id:
            status, rotated = call("POST", f"/api/v1/members/{member_id}/reset-password")
            new_password = rotated.get("password") if isinstance(rotated, dict) else None
            check("POST /members/{id}/reset-password", status == 200, f"-> {status}")
            check(
                "reset issues a different password",
                bool(new_password) and new_password != initial_password,
                f"-> len={len(new_password) if new_password else 0}",
            )
            check(
                "reset echoes the same member",
                isinstance(rotated, dict) and rotated.get("memberId") == member_id,
            )
            check("new password can log in", login(marker_email, new_password) == 200)
            # The security-relevant half: rotation must invalidate the old secret.
            check("old password is revoked", login(marker_email, initial_password) == 401)

        check(
            "reset unknown member -> 404",
            call("POST", "/api/v1/members/00000000-0000-4000-8000-0000000000ff/reset-password")[0]
            == 404,
        )

        status, _ = call(
            "POST", "/api/v1/members",
            {"email": marker_email, "displayName": "dup", "role_id": viewer["id"]},
        )
        check("POST /members duplicate -> 409", status == 409, f"-> {status}")

        status, _ = call(
            "POST", "/api/v1/members",
            {"email": f"__smoke__{int(time.time())}b@example.com", "displayName": "no role"},
        )
        check("POST /members without role -> 422", status == 422, f"-> {status}")

    # ── Workflow template publish ─────────────────────────────────────
    templates = read_data.get("/api/v1/workflow-templates")
    template_items = (
        templates.get("items", []) if isinstance(templates, dict) else (templates or [])
    )
    if template_items:
        status, published = call(
            "POST", f"/api/v1/workflow-templates/{template_items[0]['id']}/publish"
        )
        published_ok = (
            status == 200
            and isinstance(published, dict)
            and published.get("status") == "PUBLISHED"
        )
        check("POST /workflow-templates/{id}/publish", published_ok, f"-> {status}")

    print(f"\n{checks - len(failures)}/{checks} checks passed")
    if failures:
        print("Failures: " + ", ".join(failures))
    print("Tip: run scripts/cleanup_smoke_data.py to purge __smoke__ leftovers.")
    if failures:
        return 1
    print("All live API checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
