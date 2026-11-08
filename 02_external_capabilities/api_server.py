"""虚拟手机 REST API：MCP Server 通过 HTTP 访问它。"""

from fastapi import Body, FastAPI, Query
from fastapi.responses import JSONResponse

from phone_core import PhoneStore


app = FastAPI(title="Virtual Phone API")
store = PhoneStore()


def as_http(result: dict):
    if result["ok"]:
        return result
    status = 409 if result["error"]["code"] == "CALENDAR_CONFLICT" else 422
    return JSONResponse(status_code=status, content=result)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/calendar/events")
def get_calendar_events(start_time: str = Query(...), end_time: str = Query(...)):
    return as_http(store.call("get_calendar_events", {"start_time": start_time, "end_time": end_time}))


@app.post("/api/calendar/events")
def create_calendar_event(arguments: dict = Body(...)):
    return as_http(store.call("create_calendar_event", arguments))


@app.get("/api/notes")
def search_notes(keyword: str = Query("")):
    return as_http(store.call("search_notes", {"keyword": keyword}))


@app.post("/api/notes")
def create_note(arguments: dict = Body(...)):
    return as_http(store.call("create_note", arguments))
