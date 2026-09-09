"""
端到端用例的共享脚手架（3.2 / 3.3 复用）

这里只放**纯工具**；fixture 一律留在 conftest.py 由 pytest 自动发现，
避免「从哪个模块导入」影响可见性。
"""

import httpx
import pytest

# 与 scripts/init_data.py 保持一致的种子账号
ACCOUNTS = {
    "chief": ("admin", "Admin1234"),
    "duty": ("duty01", "Duty1234"),
    "maint": ("maint01", "Maint1234"),
}

# 本次运行产生的数据都以该标记开头，会话结束时统一清理
RUN_TAG = "E2E-"

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class Api:
    """带 Token 的轻量客户端封装。`unwrap` 断言 200 并直接返回统一响应体的 data 字段。"""

    def __init__(self, client: httpx.Client, token: str | None = None):
        self.client = client
        self.token = token

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = dict(kwargs.pop("headers", None) or {})
        if self.token:
            headers.setdefault("Authorization", f"Bearer {self.token}")
        return self.client.request(method, url, headers=headers, **kwargs)

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def put(self, url, **kw):
        return self.request("PUT", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)

    def unwrap(self, method: str, url: str, **kw):
        resp = self.request(method, url, **kw)
        assert resp.status_code == 200, f"{method} {url} -> {resp.status_code} {resp.text}"
        body = resp.json()
        assert body["code"] == 200, f"{method} {url} -> {body}"
        return body["data"]


def login(client: httpx.Client, role: str) -> Api:
    username, password = ACCOUNTS[role]
    resp = client.post("/auth/login", json={"username": username, "password": password})
    if resp.status_code != 200:
        pytest.skip(
            f"种子账号 {username} 登录失败（{resp.status_code} {resp.text}）"
            "，请先执行 backend/scripts/init_data.py"
        )
    return Api(client, resp.json()["data"]["access_token"])


def device_payload(code: str, types: dict, org_id: int, **overrides) -> dict:
    payload = {
        "device_code": code,
        "device_name": f"端到端设备{code}",
        "type_id": types["smoke_detector"]["id"],
        "org_id": org_id,
        "manufacturer": "霍尼韦尔",
        "brand": "Honeywell",
        "model": "XLS-PS",
        "spec": "光电型",
        "install_date": "2025-03-15",
        "warranty_expire_date": "2028-03-15",
        "maintain_cycle": 90,
        "map_x": 120.5,
        "map_y": 340.25,
        "attributes": {"sensitivity": "高", "detection_area": 60},
    }
    payload.update(overrides)
    return payload


def find_by_keyword(api: Api, keyword: str, **params) -> dict:
    query = {"keyword": keyword, "page_size": 100, "include_retired": True}
    query.update(params)
    return api.unwrap("GET", "/devices", params=query)


def total_of(api: Api, keyword: str, **params) -> int:
    return find_by_keyword(api, keyword, **params)["total"]
