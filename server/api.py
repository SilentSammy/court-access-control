"""
FastAPI server for Facility light control.
MCP-compatible with REST endpoints for managing room lights.
"""

from fastapi import FastAPI, HTTPException, Query, Body
from pydantic import BaseModel
from typing import List
import asyncio
import logging
try:
    from server.facility import FacilityManager
    from server.device_discoverer import DeviceDiscoverer
except ImportError:
    from facility import FacilityManager
    from device_discoverer import DeviceDiscoverer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Facility Light Control API",
    description="Control facility lights through MCP-compatible REST endpoints",
    version="1.0"
)

# Initialize facility manager
# Note: This will auto-discover devices including mock server on localhost:800x
facility_manager = FacilityManager(
    discoverer=DeviceDiscoverer(
        discovery_interval=10,
        health_check_interval=5,
        check_localhost=True,
        scan_networks=[
            "192.168.137.0/24",  # Windows hotspot
            "192.168.1.0/24"     # Home network (check ipconfig at home)
        ]
    )
)

# Start discovery on startup
@app.on_event("startup")
async def startup_event():
    """Start device discovery when API starts."""
    logger.info("Starting device discovery...")
    facility_manager.start_discovery()
    
    # Run initial discovery immediately
    await facility_manager.discoverer.discover_devices()
    
    # Wait a bit for discovery results
    await asyncio.sleep(1)
    
    rooms = facility_manager.get_room_ids()
    logger.info(f"Discovery complete. Available rooms: {rooms}")
    
    if not rooms:
        logger.warning("No rooms discovered! Check if mock server is running on localhost")

@app.on_event("shutdown")
async def shutdown_event():
    """Stop device discovery when API shuts down."""
    logger.info("Stopping device discovery...")
    facility_manager.stop_discovery()
    await asyncio.sleep(0.5)
    logger.info("Discovery stopped.")

# Pydantic models (for responses only)
class RoomStatus(BaseModel):
    """Room status response."""
    room: int
    light: str  # "on" or "off"

class RoomStatusDetailed(BaseModel):
    """Detailed room status response."""
    room: int
    light: str

class DiscoveryStatus(BaseModel):
    """Discovery status response."""
    running: bool
    devices_found: int
    endpoints_found: int
    rooms_available: List[str]

class BatchLightControl(BaseModel):
    """Request model for batch light control."""
    room_ids: Optional[List[str]] = None  # None means all rooms
    state: int  # 1=on, 0=off

# ============================================================================
# RESOURCES (GET - Read-only for MCP)
# ============================================================================

@app.get("/")
def root():
    """Root endpoint with API info."""
    return {
        "api": "Facility Light Control",
        "version": "1.0",
        "endpoints": {
            "resources": [
                "GET /rooms",
                "GET /rooms/{room_id}/status",
                "GET /discovery/status"
            ],
            "tools": [
                "POST /rooms/{room_id}/lights (body: {state: 1})",
                "POST /rooms/lights/control (body: {room_ids: [], state: 1})"
            ]
        }
    }

@app.get("/rooms", response_model=dict)
def get_rooms():
    """Get all available room IDs.
    
    MCP Resource: List of controllable rooms.
    """
    rooms = facility_manager.get_room_ids()
    return {
        "rooms": rooms,
        "count": len(rooms)
    }

@app.get("/rooms/{room_id}/status", response_model=RoomStatusDetailed)
async def get_room_status(room_id: str):
    """Get current status of a room.
    
    MCP Resource: Current light state for a room.
    """
    if room_id not in facility_manager.get_room_ids():
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")
    
    result = await facility_manager.get_room_status(room_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return RoomStatusDetailed(
        room=int(room_id),
        light=result.get("light", "unknown")
    )

@app.get("/discovery/status", response_model=DiscoveryStatus)
def get_discovery_status():
    """Get device discovery status.
    
    MCP Resource: Current discovery state and available devices.
    """
    devices = facility_manager.discoverer.get_devices()
    endpoints = facility_manager.discoverer.get_all_endpoints()
    
    return DiscoveryStatus(
        running=facility_manager.discoverer._running,
        devices_found=len(devices),
        endpoints_found=len(endpoints),
        rooms_available=facility_manager.get_room_ids()
    )

# ============================================================================
# TOOLS (POST - Actions for MCP)
# ============================================================================

@app.post("/rooms/{room_id}/lights", response_model=RoomStatus)
async def control_room_lights(
    room_id: str,
    state: int = Body(..., embed=True, description="1=on, 0=off")
):
    """Control lights in a specific room.
    
    MCP Tool: Turn lights on/off.
    
    Args:
        room_id: Room identifier (path parameter)
        state: Light state - 1 for on, 0 for off (body parameter)
    """
    if room_id not in facility_manager.get_room_ids():
        raise HTTPException(status_code=404, detail=f"Room {room_id} not found")
    
    result = await facility_manager.control_lights(room_id, state == 1)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return RoomStatus(
        room=int(room_id),
        light=result.get("light", "unknown")
    )



@app.post("/rooms/lights/control", response_model=List[RoomStatus])
async def batch_control_lights(
    room_ids: List[str] = Body(..., description="List of room IDs (empty array to control all rooms)"),
    state: int = Body(..., description="1=on, 0=off")
):
    """Control lights in multiple rooms at once.
    
    MCP Tool: Batch light control operation.
    
    Args:
        room_ids: List of room IDs to control, or empty array to control all rooms (body parameter)
        state: Light state - 1 for on, 0 for off (body parameter)
    
    Returns array of results for each room.
    """
    # If room_ids is empty, use all available rooms (sentinel value)
    if not room_ids:
        room_ids = facility_manager.get_room_ids()
        if not room_ids:
            raise HTTPException(status_code=400, detail="No rooms available")
    
    available_rooms = facility_manager.get_room_ids()
    invalid_rooms = [r for r in room_ids if r not in available_rooms]
    if invalid_rooms:
        raise HTTPException(
            status_code=404,
            detail=f"Rooms not found: {invalid_rooms}"
        )
    
    results = []
    for room_id in room_ids:
        result = await facility_manager.control_lights(room_id, state == 1)
        
        if "error" not in result:
            results.append(RoomStatus(
                room=int(room_id),
                light=result.get("light", "unknown")
            ))
    
    return results



# ============================================================================
# MCP Wrapper (if needed)
# ============================================================================

# Uncomment to add MCP support (requires fastapi_mcp package)
# from fastapi_mcp import FastApiMCP
# mcp_app = FastApiMCP(app)
# mcp_app.mount_http()

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*60)
    print("Facility Light Control API")
    print("="*60)
    print("\nStarting server on localhost")
    print("\nEndpoints:")
    print("  Resources (GET):")
    print("    GET  /rooms                      - List available rooms")
    print("    GET  /rooms/{room_id}/status     - Get room light status")
    print("    GET  /discovery/status           - Get discovery status")
    print("\n  Tools (POST):")
    print("    POST /rooms/{room_id}/lights         - Control lights (body: {\"state\": 1})")
    print("    POST /rooms/lights/control           - Batch control (body: {\"room_ids\": [\"1\",\"2\"], \"state\": 1})")
    print("\n  Info:")
    print("    GET  /                           - API info")
    print("    GET  /docs                       - Swagger UI (interactive)")
    print("    GET  /redoc                      - ReDoc (API documentation)")
    print("\n" + "="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)
