# FastAPI Bot Server Setup Guide

This guide explains how to set up FastAPI endpoints for compatibility with the `ToolEnabledHttpClient` bot framework.

## Overview

The `ToolEnabledHttpClient` automatically generates HTTP client methods and LLM tools from FastAPI endpoints. It introspects endpoint signatures to determine parameter handling.

## Endpoint Parameter Rules

### Path Parameters
Use **path parameters** for resource identifiers that appear in the URL:

```python
@app.get("/rooms/{room_id}/status")
async def get_room_status(room_id: str):
    """Get room status by ID"""
    # room_id is extracted from URL: /rooms/1/status
    return {"room": room_id, "status": "on"}
```

**Client call:**
```python
await http_client.get_client_method("get_room_status")(room_id="1")
# → GET /rooms/1/status
```

### GET Query Parameters
For GET requests, non-path parameters become query parameters:

```python
@app.get("/rooms")
def get_rooms(limit: int = 10, offset: int = 0):
    """Get all rooms with pagination"""
    # limit and offset become query params
    return {"rooms": [...]}
```

**Client call:**
```python
await http_client.get_client_method("get_rooms")(limit=5, offset=0)
# → GET /rooms?limit=5&offset=0
```

### POST Body Parameters (Single Parameter)
For a single body parameter, use `Body(..., embed=True)`:

```python
from fastapi import Body

@app.post("/rooms/{room_id}/lights")
async def control_room_lights(
    room_id: str,
    state: int = Body(..., embed=True, description="1=on, 0=off")
):
    """Control lights in a room"""
    # room_id is path param, state is body param
    return {"room": room_id, "light": "on" if state else "off"}
```

**Important:** The `embed=True` parameter tells FastAPI to expect the value wrapped in a JSON object:

```json
POST /rooms/1/lights
{"state": 0}
```

**Client call:**
```python
await http_client.get_client_method("control_room_lights")(room_id="1", state=0)
# → POST /rooms/1/lights with body: {"state": 0}
```

### POST Body Parameters (Multiple Parameters)
For multiple body parameters, no `embed=True` needed—FastAPI handles it automatically:

```python
@app.post("/rooms/lights/control")
async def batch_control_lights(
    room_ids: List[str] = Body(..., description="Room IDs"),
    state: int = Body(..., description="1=on, 0=off")
):
    """Control multiple rooms at once"""
    # Both room_ids and state are body params
    return [{"room": r, "light": "on" if state else "off"} for r in room_ids]
```

**Client call:**
```python
await http_client.get_client_method("batch_control_lights")(room_ids=["1", "2"], state=1)
# → POST /rooms/lights/control with body: {"room_ids": ["1", "2"], "state": 1}
```

## Pydantic Models (Optional)
You can also use Pydantic models for structured request bodies:

```python
from pydantic import BaseModel

class LightControl(BaseModel):
    state: int

@app.post("/rooms/{room_id}/lights")
async def control_room_lights(
    room_id: str,
    control: LightControl  # Pydantic model as body
):
    """Control lights using a model"""
    return {"room": room_id, "light": "on" if control.state else "off"}
```

**Client call:** Same as above—`ToolEnabledHttpClient` handles unwrapping Pydantic models automatically.

## Response Models
Always use Pydantic models for response validation:

```python
from pydantic import BaseModel

class RoomStatus(BaseModel):
    room: int
    light: str  # "on" or "off"

@app.get("/rooms/{room_id}/status", response_model=RoomStatus)
async def get_room_status(room_id: str) -> RoomStatus:
    """Get room status with type validation"""
    return RoomStatus(room=int(room_id), light="on")
```

## Bot Registration

In your bot setup file (e.g., `facility_bot.py`):

```python
from server.api import app, get_rooms, get_room_status, control_room_lights, batch_control_lights
from bot.client import ToolEnabledHttpClient

# Create client
http_client = ToolEnabledHttpClient(app, base_url="http://localhost:8000")

# Register endpoints as tools
endpoints = [
    get_rooms,
    get_room_status,
    control_room_lights,
    batch_control_lights,
]
http_client.register_endpoints(endpoints)

# Use tools in agent
tools = http_client.get_all_tools()
```

## Common Mistakes

❌ **Don't:** Forget `embed=True` for single body parameters
```python
# Wrong - will send just the value
state: int = Body(...)
```

✅ **Do:** Include `embed=True` for single body parameters
```python
# Correct - wraps in {"state": value}
state: int = Body(..., embed=True)
```

❌ **Don't:** Use Query() for POST body parameters
```python
# Wrong - FastAPI treats this as query param
@app.post("/rooms/{room_id}/lights")
async def control_room_lights(room_id: str, state: int = Query(...)):
```

✅ **Do:** Use Body() for POST body parameters
```python
# Correct - FastAPI treats this as body param
@app.post("/rooms/{room_id}/lights")
async def control_room_lights(room_id: str, state: int = Body(..., embed=True)):
```

## Testing

Start the server:
```bash
python api.py
```

The API will be available at:
- **Base URL:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

Use Swagger UI to test endpoints before integrating with the bot.

## Summary

| Scenario | Syntax | HTTP |
|----------|--------|------|
| Path ID | `room_id: str` (in path) | `/rooms/1` |
| GET query | `limit: int = 10` (GET endpoint) | `?limit=10` |
| POST single body | `state: int = Body(..., embed=True)` | `{"state": 1}` |
| POST multiple body | `state: int = Body(...)` + others | `{"state": 1, ...}` |
| Response validation | `response_model=RoomStatus` | Always include |
