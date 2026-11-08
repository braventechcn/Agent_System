"""验证真实业务规则与 REST 入口的关键边界。"""

import asyncio

import httpx
from fastapi.testclient import TestClient

import agent
import api_server
from phone_core import PhoneStore


WINDOW = {
    "start_time": "2026-11-09T10:00:00+08:00",
    "end_time": "2026-11-09T11:00:00+08:00",
}


def test_overlap_and_touching_boundary():
    phone = PhoneStore()
    assert phone.call("get_calendar_events", WINDOW)["data"]["count"] == 1
    later = {"start_time": "2026-11-09T11:30:00+08:00", "end_time": "2026-11-09T12:00:00+08:00"}
    assert phone.call("get_calendar_events", later)["data"]["count"] == 0


def test_reject_bad_time_and_conflict_without_mutation():
    phone = PhoneStore()
    naive = phone.call("get_calendar_events", {
        "start_time": "2026-11-09T10:00:00", "end_time": "2026-11-09T11:00:00",
    })
    assert naive["error"]["code"] == "INVALID_TIME"
    conflicting = phone.call("create_calendar_event", {"title": "重复会议", **WINDOW})
    assert conflicting["error"]["code"] == "CALENDAR_CONFLICT"
    assert len(phone.events) == 1


def test_note_creation_and_search():
    phone = PhoneStore()
    created = phone.call("create_note", {"title": "周计划", "content": "整理下周任务"})
    assert created["data"]["note"]["id"] == "note_002"
    found = phone.call("search_notes", {"keyword": "周计划"})
    assert found["data"]["count"] == 1
    assert phone.call("search_notes", {"keyword": "评审"})["data"]["count"] == 1


def test_unknown_tool_and_extra_argument():
    phone = PhoneStore()
    assert phone.call("delete_all", {})["error"]["code"] == "TOOL_NOT_ALLOWED"
    assert phone.call("get_calendar_events", {**WINDOW, "admin": "yes"})["error"]["code"] == "INVALID_ARGUMENTS"


def test_rest_api_uses_same_rules(monkeypatch):
    monkeypatch.setattr(api_server, "store", PhoneStore())
    client = TestClient(api_server.app)
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/api/calendar/events", params=WINDOW)
    assert response.status_code == 200
    assert response.json()["data"]["events"][0]["title"] == "产品评审会议"
    conflict = client.post("/api/calendar/events", json={"title": "重复会议", **WINDOW})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "CALENDAR_CONFLICT"
    bad = client.get("/api/calendar/events", params={"start_time": "not-a-date", "end_time": WINDOW["end_time"]})
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "INVALID_TIME"


def test_rest_backend_maps_tools_and_preserves_business_errors(monkeypatch):
    """让 RESTBackend 走真实 ASGI 路由，检查 HTTP 映射与错误回传。"""
    monkeypatch.setattr(api_server, "store", PhoneStore())
    real_client = httpx.AsyncClient

    def asgi_client(*args, **kwargs):
        # 用内存中的 ASGI 服务替代 TCP，仍经过 RESTBackend 的 HTTP 请求构造。
        return real_client(*args, transport=httpx.ASGITransport(app=api_server.app), **kwargs)

    monkeypatch.setattr(agent.httpx, "AsyncClient", asgi_client)
    backend = agent.RESTBackend("http://testserver")

    async def exercise():
        assert await backend.tools() == agent.TOOLS
        found = await backend.call("get_calendar_events", WINDOW)
        assert found["data"]["events"][0]["title"] == "产品评审会议"
        conflict = await backend.call("create_calendar_event", {"title": "重复会议", **WINDOW})
        assert conflict["error"]["code"] == "CALENDAR_CONFLICT"
        created = await backend.call("create_note", {"title": "周计划", "content": "整理下周任务"})
        assert created["data"]["note"]["id"] == "note_002"
        notes = await backend.call("search_notes", {"keyword": "周计划"})
        assert notes["data"]["count"] == 1
        denied = await backend.call("delete_all", {})
        assert denied["error"]["code"] == "TOOL_NOT_ALLOWED"

    asyncio.run(exercise())
