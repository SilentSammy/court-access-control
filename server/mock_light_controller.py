"""
FastAPI mock server that simulates the MicroPython light controller device.
Useful for development and testing without physical hardware.

The mock device has the same endpoints and behavior as the actual IoT device:
- Lights are ACTIVE LOW (0/LOW = ON, 1/HIGH = OFF)
- All lights start OFF (value=1)
"""

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from typing import Optional

app = FastAPI(title="Mock Light Controller", version="1.0")

# Light state: 0 = ON (LOW), 1 = OFF (HIGH)
# Initialize all lights to OFF (1)
light_state = {
    1: 1,  # Room 1: OFF
    2: 1,  # Room 2: OFF
    3: 1,  # Room 3: OFF
}


@app.get("/device-info")
def device_info():
    """Return device information for discovery"""
    return {
        "device_type": "light_controller",
        "endpoints": ["1/lights", "2/lights", "3/lights"]
    }


@app.get("/{room}/lights")
def handle_lights(
    room: int,
    state: Optional[int] = Query(None, description="Set state (1=on, 0=off)"),
    toggle: Optional[int] = Query(None, description="Toggle light (1=toggle)")
):
    """
    Handle light operations for a specific room.
    
    Query parameters:
    - No params: Get status (read-only)
    - state=1: Turn ON
    - state=0: Turn OFF
    - toggle=1: Toggle
    
    Note: Lights are ACTIVE LOW (0 = ON, 1 = OFF)
    """
    
    if room not in light_state:
        return JSONResponse(
            status_code=404,
            content={"error": f"Room {room} not found. Valid rooms: 1, 2, 3"}
        )
    
    action = "status"
    
    # Handle toggle request
    if toggle == 1:
        light_state[room] = 1 - light_state[room]
        action = "toggled"
    # Handle state change request
    elif state is not None:
        light_state[room] = 1 - state  # Invert for active low (state 1 means ON, which is 0 in hardware)
        action = "on" if state else "off"
    
    # Return current state (inverted back for readability)
    return {
        "room": room,
        "light": "on" if light_state[room] == 0 else "off",
        "action": action
    }


@app.get("/")
def root():
    """Root endpoint with usage instructions"""
    return {
        "device": "Mock Light Controller",
        "endpoints": {
            "/device-info": "Get device information",
            "/{room}/lights": "Get/control light (room: 1-3)",
        },
        "examples": {
            "get_status": "GET /1/lights",
            "turn_on": "GET /1/lights?state=1",
            "turn_off": "GET /1/lights?state=0",
            "toggle": "GET /1/lights?toggle=1"
        }
    }


@app.get("/status")
def get_all_status():
    """Get status of all lights"""
    return {
        "rooms": {
            room: "on" if state == 0 else "off"
            for room, state in light_state.items()
        }
    }


if __name__ == "__main__":
    import uvicorn
    port = 8001
    print(f"Starting Mock Light Controller on http://localhost:{port}")
    print("\nEndpoints:")
    print(f"  GET http://localhost:{port}/device-info")
    print(f"  GET http://localhost:{port}/status (all rooms)")
    print(f"  GET http://localhost:{port}/1/lights (room 1)")
    print(f"  GET http://localhost:{port}/1/lights?state=1 (turn on)")
    print(f"  GET http://localhost:{port}/1/lights?state=0 (turn off)")
    print(f"  GET http://localhost:{port}/1/lights?toggle=1 (toggle)")
    print("\n")
    uvicorn.run(app, host="127.0.0.1", port=port)
