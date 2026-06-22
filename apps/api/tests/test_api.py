"""
API 冒烟与契约测试（不依赖 图谱存储 / LLM）。

覆盖：健康检查、三大路由可达、统一信封、i18n（Accept-Language）、
必填项校验返回 400（而非 FastAPI 默认 422）、路由顺序正确。
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client(auth_headers) -> TestClient:
    """已登录的测试客户端：业务路由均要求鉴权，默认带上 access token 头。"""
    c = TestClient(app)
    c.headers.update(auth_headers)
    return c


def test_health(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_project_list_envelope(client: TestClient):
    """字面量路由 /project/list 不被 /{project_id} 吞掉，返回统一信封。"""
    r = client.get("/api/graph/project/list")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


def test_unknown_project_localized_zh(client: TestClient):
    r = client.get("/api/graph/project/__nope__")
    assert r.status_code == 404
    assert r.json()["success"] is False
    assert "不存在" in r.json()["error"]


def test_unknown_project_localized_en(client: TestClient):
    r = client.get("/api/graph/project/__nope__", headers={"Accept-Language": "en"})
    assert r.status_code == 404
    assert "not found" in r.json()["error"].lower()


def test_utf8_chinese_direct(client: TestClient):
    """中文应 UTF-8 直出，而非 \\uXXXX 转义。"""
    raw = client.get("/api/graph/project/__nope__").content.decode("utf-8")
    assert "项目" in raw


def test_required_field_returns_400_not_422(client: TestClient):
    """缺必填项应返回本地化 400，而非 FastAPI 默认 422。"""
    r = client.post("/api/graph/build", json={})
    assert r.status_code == 400
    assert r.json()["success"] is False


def test_simulation_create_validation(client: TestClient):
    r = client.post("/api/simulation/create", json={})
    assert r.status_code == 400
    assert r.json()["success"] is False


def test_simulation_list_reachable(client: TestClient):
    r = client.get("/api/simulation/list")
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_simulation_history_reachable(client: TestClient):
    """/history 命中 lifecycle 子路由（其内联导入深度正确，不被 /{simulation_id} 吞）。"""
    r = client.get("/api/simulation/history")
    assert r.status_code == 200
    assert r.json()["success"] is True


def test_simulation_catchall_unknown_404(client: TestClient):
    """单段 catch-all /{simulation_id} 注册在最后：未知 id 经归属守卫返回 404。"""
    r = client.get("/api/simulation/__nope__")
    assert r.status_code == 404


def test_simulation_subrouters_reachable(client: TestClient):
    """run/interview/env 子路由可达：空体命中处理器并返回本地化 400（非 404/500）。"""
    for path in ("/api/simulation/stop", "/api/simulation/interview", "/api/simulation/env-status"):
        r = client.post(path, json={})
        assert r.status_code == 400, f"{path} -> {r.status_code}"
        assert r.json()["success"] is False


def test_report_list_reachable(client: TestClient):
    r = client.get("/api/report/list")
    assert r.status_code == 200
    assert r.json()["success"] is True


def _create_user(email: str, password: str, *, verified: bool = True) -> str:
    """直接落库一个用户，返回 user_id（用于鉴权相关用例）。"""
    import time
    import uuid

    from app.core.db import session_scope
    from app.core.security import hash_password
    from app.db_models import UserRow

    user_id = f"user_login_{uuid.uuid4().hex[:10]}"
    now = str(int(time.time()))
    with session_scope() as session:
        session.add(
            UserRow(
                user_id=user_id,
                email=email,
                password_hash=hash_password(password),
                display_name="login-test",
                status="active",
                email_verified=verified,
                created_at=now,
                updated_at=now,
            )
        )
    return user_id


def test_auth_login_success_and_me():
    """登录走 UserRepository.get_by_email；/me 走 get_current_user。"""
    import uuid

    c = TestClient(app)
    email = f"login_{uuid.uuid4().hex[:8]}@test.local"
    _create_user(email, "secret-pass-123")

    r = c.post("/api/auth/login", json={"email": email, "password": "secret-pass-123"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    access = body["data"]["access_token"]
    refresh = body["data"]["refresh_token"]
    assert body["data"]["user"]["email"] == email

    me = c.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["data"]["email"] == email

    # refresh 走 UserRepository.get_by_id
    rr = c.post("/api/auth/refresh", json={"refresh_token": refresh})
    assert rr.status_code == 200
    assert rr.json()["data"]["access_token"]


def test_auth_login_wrong_password():
    import uuid

    c = TestClient(app)
    email = f"login_{uuid.uuid4().hex[:8]}@test.local"
    _create_user(email, "secret-pass-123")
    r = c.post("/api/auth/login", json={"email": email, "password": "WRONG"})
    assert r.status_code == 401
    assert r.json()["success"] is False


def test_auth_validation_400():
    c = TestClient(app)
    assert c.post("/api/auth/login", json={}).status_code == 400
    assert c.post("/api/auth/refresh", json={}).status_code == 400


def test_auth_me_requires_auth():
    c = TestClient(app)
    assert c.get("/api/auth/me").status_code == 401


def test_openapi_route_counts(client: TestClient):
    """三大路由端点数量符合预期（防止路由意外丢失）。"""
    paths = client.get("/openapi.json").json()["paths"]
    graph = [p for p in paths if p.startswith("/api/graph")]
    report = [p for p in paths if p.startswith("/api/report")]
    sim = [p for p in paths if p.startswith("/api/simulation")]
    assert len(graph) == 10
    assert len(report) == 17
    assert len(sim) == 37
