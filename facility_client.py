"""
Facility-specific HTTP client with pre-registered endpoints.

Extends ToolEnabledHttpClient with automatic endpoint registration for
facility light control operations.
"""

from typing import List
from bot.client import ToolEnabledHttpClient


class FacilityHttpClient(ToolEnabledHttpClient):
    """
    Pre-configured HTTP client for Facility Light Control API.
    
    Automatically imports and registers all facility endpoints.
    Exposes them as methods.
    
    Usage:
        # Create with default base_url
        client = FacilityHttpClient()
        
        # Or specify custom base_url
        client = FacilityHttpClient(base_url="http://localhost:8000")
        
        # Access as methods:
        rooms = await client.get_rooms()
        status = await client.get_room_status(room_id="1")
        result = await client.control_room_lights(room_id="1", state=1)
        
        # Or get tools for bot:
        tools = client.get_all_tools()
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize Facility HTTP client and auto-register endpoints.
        
        Args:
            base_url: Base URL of the server (default: http://localhost:8000)
        """
        # Import facility app and endpoints
        try:
            from server.api import (
                app as facility_app,
                get_rooms,
                get_room_status,
                get_discovery_status,
                control_room_lights,
                batch_control_lights,
            )
        except ImportError:
            try:
                from api import (
                    app as facility_app,
                    get_rooms,
                    get_room_status,
                    get_discovery_status,
                    control_room_lights,
                    batch_control_lights,
                )
            except ImportError as e:
                raise ImportError(
                    "Could not import facility API from server.api or api"
                ) from e
        
        super().__init__(facility_app, base_url)
        
        # Register all facility endpoints
        self.register_endpoints([
            get_rooms,
            get_room_status,
            get_discovery_status,
            control_room_lights,
            batch_control_lights,
        ])
        
        # Store endpoint names for quick reference
        self._endpoint_names = {
            "get_rooms",
            "get_room_status",
            "get_discovery_status",
            "control_room_lights",
            "batch_control_lights",
        }
    
    # Convenience methods to access endpoints as attributes
    
    async def get_rooms(self) -> dict:
        """Get all available room IDs."""
        method = self.get_client_method("get_rooms")
        return await method()
    
    async def get_room_status(self, room_id: str) -> dict:
        """Get current status of a room."""
        method = self.get_client_method("get_room_status")
        return await method(room_id=room_id)
    
    async def get_discovery_status(self) -> dict:
        """Get device discovery status."""
        method = self.get_client_method("get_discovery_status")
        return await method()
    
    async def control_room_lights(self, room_id: str, state: int) -> dict:
        """
        Control lights in a specific room.
        
        Args:
            room_id: Room identifier
            state: 1 for on, 0 for off
        
        Returns:
            Room status after control
        """
        method = self.get_client_method("control_room_lights")
        return await method(room_id=room_id, state=state)
    
    async def batch_control_lights(self, room_ids: List[str] = None, state: int = 1) -> list:
        """
        Control lights in multiple rooms at once.
        
        Args:
            room_ids: List of room IDs to control, or empty list to control all rooms (default: empty list)
            state: 1 for on, 0 for off (default: 1)
        
        Returns:
            List of room statuses after control
        """
        if room_ids is None:
            room_ids = []
        method = self.get_client_method("batch_control_lights")
        return await method(room_ids=room_ids, state=state)
    
    def get_facility_tools(self) -> list:
        """
        Get only the facility API tools (excluding any other tools).
        
        Returns:
            List of FunctionTool objects for facility endpoints
        """
        return [
            self.get_tool(name)
            for name in self._endpoint_names
            if self.get_tool(name) is not None
        ]


if __name__ == "__main__":
    """Example usage of FacilityHttpClient"""
    import asyncio
    
    async def demo():
        print("\n" + "="*70)
        print("FacilityHttpClient Demo")
        print("="*70)
        
        # Create client
        print("\n1. Creating FacilityHttpClient...")
        try:
            client = FacilityHttpClient(base_url="http://localhost:8000")
            print("✓ Client created and endpoints registered")
        except Exception as e:
            print(f"✗ Error: {e}")
            return
        
        # Test endpoints
        print("\n2. Testing get_rooms()...")
        try:
            rooms = await client.get_rooms()
            print(f"✓ Rooms: {rooms}")
        except Exception as e:
            print(f"✗ Error: {e}")
        
        print("\n3. Testing get_room_status()...")
        try:
            status = await client.get_room_status(room_id="1")
            print(f"✓ Room 1 status: {status}")
        except Exception as e:
            print(f"✗ Error: {e}")
        
        print("\n4. Testing control_room_lights()...")
        try:
            result = await client.control_room_lights(room_id="1", state=0)
            print(f"✓ Control result: {result}")
        except Exception as e:
            print(f"✗ Error: {e}")
        
        print("\n5. Testing get_facility_tools()...")
        try:
            tools = client.get_facility_tools()
            print(f"✓ Generated {len(tools)} tools:")
            for tool in tools:
                print(f"  - {tool.name}")
        except Exception as e:
            print(f"✗ Error: {e}")
        
        print("\n" + "="*70)
        print("✅ Demo complete!")
        print("="*70)
    
    asyncio.run(demo())
