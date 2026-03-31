# EXAMPLES
#   http://192.168.137.133/1/lights?state=1  (turn on room 1)
#   http://192.168.137.133/1/lights?state=0  (turn off room 1)
#   http://192.168.137.133/1/lights          (toggle room 1)

from device_discoverer import DeviceDiscoverer
import asyncio
import aiohttp
import json

async def _http_request(url):
    """Send HTTP GET request, return dict if JSON else string."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                data = await response.text()
                try:
                    return json.loads(data)
                except json.JSONDecodeError:
                    return data
    except asyncio.TimeoutError:
        return {"error": f"Timeout connecting to {url}"}
    except Exception as e:
        return {"error": f"Request failed: {type(e).__name__}: {str(e)}"}

class FacilityManager:
    """Manages IoT devices using DeviceDiscoverer."""
    
    def __init__(self, mock=False, discoverer=None):
        """Initialize with device discoverer.
        
        Args:
            mock: If True, returns mock responses without actual device communication
            discoverer: DeviceDiscoverer instance. If None, creates default with sensible settings.
        """
        self.mock = mock
        self.discoverer = discoverer or DeviceDiscoverer()
    
    def start_discovery(self):
        """Start background device discovery."""
        self.discoverer.start_continuous_discovery()
    
    def stop_discovery(self):
        """Stop background device discovery."""
        self.discoverer.stop_continuous_discovery()
    
    async def control_lights(self, room_id, state):
        """Control room lights by ID."""
        endpoint = f"{room_id}/lights"
        
        if not self.discoverer.endpoint_exists(endpoint):
            return {"error": f"Room {room_id} not found"}
        
        if self.mock:
            return {
                "room": int(room_id),
                "light": "on" if state else "off",
                "action": "on" if state else "off"
            }
        
        url = self.discoverer.complete_url(endpoint)
        url = f"{url}?state={1 if state else 0}"
        return await _http_request(url)
    
    async def get_room_status(self, room_id):
        """Get current status of a room by ID."""
        endpoint = f"{room_id}/lights"
        
        if not self.discoverer.endpoint_exists(endpoint):
            return {"error": f"Room {room_id} not found"}
        
        if self.mock:
            return {
                "room": int(room_id),
                "light": "on",
                "action": "toggled"
            }
        
        url = self.discoverer.complete_url(endpoint)
        return await _http_request(url)

async def _demo():
    """Demo showing FacilityManager usage."""
    # Configure discoverer separately for more control
    discoverer = DeviceDiscoverer(
        discovery_interval=30,
        health_check_interval=5,
        scan_networks=["192.168.137.0/24"]  # Only scan hotspot at school
    )
    
    manager = FacilityManager(discoverer=discoverer)
    
    print("=== FacilityManager Demo ===")
    print("Starting device discovery...")
    manager.start_discovery()
    
    print("Waiting for devices to be discovered...\n")
    
    try:
        while True:
            endpoints = manager.discoverer.get_all_endpoints()
            light_endpoints = [e for e in endpoints if e.endswith('/lights')]
            
            if light_endpoints:
                print(f"Found {len(light_endpoints)} light controls")
                
                for endpoint in light_endpoints:
                    room_id = endpoint.split('/')[0]
                    
                    # Turn on
                    result = await manager.control_lights(room_id, True)
                    print(f"  Room {room_id} ON: {result}")
                    
                    await asyncio.sleep(1)
                    
                    # Turn off
                    result = await manager.control_lights(room_id, False)
                    print(f"  Room {room_id} OFF: {result}")
                
                print()
            
            await asyncio.sleep(10)
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
        manager.stop_discovery()
        await asyncio.sleep(1)
        print("Stopped.")

if __name__ == "__main__":
    asyncio.run(_demo())
