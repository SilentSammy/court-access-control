# EXAMPLES
#   LIGHTS:
#   http://192.168.137.133/1/lights           (get status room 1)
#   http://192.168.137.133/1/lights?state=1   (turn on room 1)
#   http://192.168.137.133/1/lights?state=0   (turn off room 1)
#   http://192.168.137.133/1/lights?toggle=1  (toggle room 1)
#
#   LOCKS:
#   http://192.168.137.133/1/lock             (get lock status room 1)
#   http://192.168.137.133/1/lock?state=1     (lock room 1)
#   http://192.168.137.133/1/lock?state=0     (unlock room 1)
#
#   COUNTDOWN:
#   http://192.168.137.133/1/countdown        (get countdown status room 1)
#   http://192.168.137.133/1/countdown?s=60   (set 60s countdown room 1)

from device_discoverer import DeviceDiscoverer
import asyncio
import aiohttp
import json

async def _http_request(url):
    """Send HTTP GET request, return dict if JSON else string."""
    try:
        # Use connector with force_close to avoid Windows connection errors
        connector = aiohttp.TCPConnector(force_close=True)
        async with aiohttp.ClientSession(connector=connector) as session:
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
    
    async def control_lock(self, room_id, state):
        """Control room lock by ID.
        
        Args:
            room_id: Room identifier
            state: True to lock, False to unlock
        """
        endpoint = f"{room_id}/lock"
        
        if not self.discoverer.endpoint_exists(endpoint):
            return {"error": f"Room {room_id} lock not found"}
        
        if self.mock:
            return {
                "room": int(room_id),
                "lock": "locked" if state else "unlocked",
                "action": "locked" if state else "unlocked"
            }
        
        url = self.discoverer.complete_url(endpoint)
        url = f"{url}?state={1 if state else 0}"
        return await _http_request(url)
    
    async def set_countdown(self, room_id, seconds):
        """Set countdown timer for a room.
        
        Args:
            room_id: Room identifier
            seconds: Number of seconds for countdown
        """
        endpoint = f"{room_id}/countdown"
        
        if not self.discoverer.endpoint_exists(endpoint):
            return {"error": f"Room {room_id} countdown not found"}
        
        if self.mock:
            return {
                "room": int(room_id),
                "countdown_remaining": seconds,
                "action": "set"
            }
        
        url = self.discoverer.complete_url(endpoint)
        url = f"{url}?s={seconds}"
        return await _http_request(url)
    
    async def get_countdown(self, room_id):
        """Get current countdown status for a room.
        
        Args:
            room_id: Room identifier
        """
        endpoint = f"{room_id}/countdown"
        
        if not self.discoverer.endpoint_exists(endpoint):
            return {"error": f"Room {room_id} countdown not found"}
        
        if self.mock:
            return {
                "room": int(room_id),
                "countdown_remaining": 0,
                "action": "status"
            }
        
        url = self.discoverer.complete_url(endpoint)
        return await _http_request(url)
    
    async def get_room_status(self, room_id):
        """Get current status of a room by ID (read-only).
        
        Returns status for lights, locks, and countdown if available.
        """
        status = {"room": int(room_id)}
        
        # Check for lights
        lights_endpoint = f"{room_id}/lights"
        if self.discoverer.endpoint_exists(lights_endpoint):
            if self.mock:
                status["light"] = "on"
            else:
                url = self.discoverer.complete_url(lights_endpoint)
                result = await _http_request(url)
                if "light" in result:
                    status["light"] = result["light"]
        
        # Check for locks
        lock_endpoint = f"{room_id}/lock"
        if self.discoverer.endpoint_exists(lock_endpoint):
            if self.mock:
                status["lock"] = "locked"
            else:
                url = self.discoverer.complete_url(lock_endpoint)
                result = await _http_request(url)
                if "lock" in result:
                    status["lock"] = result["lock"]
        
        # Check for countdown
        countdown_endpoint = f"{room_id}/countdown"
        if self.discoverer.endpoint_exists(countdown_endpoint):
            if self.mock:
                status["countdown_remaining"] = 0
            else:
                url = self.discoverer.complete_url(countdown_endpoint)
                result = await _http_request(url)
                if "countdown_remaining" in result:
                    status["countdown_remaining"] = result["countdown_remaining"]
        
        # Return error if no endpoints found
        if len(status) == 1:  # Only has "room" key
            return {"error": f"Room {room_id} not found"}
        
        return status

async def _demo():
    """Demo showing FacilityManager usage."""
    manager = FacilityManager(discoverer=DeviceDiscoverer(
        discovery_interval=30,
        health_check_interval=5,
        scan_networks=[
            "192.168.137.0/24",  # Windows hotspot
            "192.168.1.0/24"     # Home network
        ]
    ))
    
    print("=== FacilityManager Demo ===")
    print("Starting device discovery...")
    manager.start_discovery()
    
    print("Waiting for devices to be discovered...\n")
    
    try:
        while True:
            endpoints = manager.discoverer.get_all_endpoints()
            light_endpoints = [e for e in endpoints if e.endswith('/lights')]
            lock_endpoints = [e for e in endpoints if e.endswith('/lock')]
            countdown_endpoints = [e for e in endpoints if e.endswith('/countdown')]
            
            if light_endpoints:
                print(f"Found {len(light_endpoints)} light controls")
                
                for endpoint in light_endpoints:
                    room_id = endpoint.split('/')[0]
                    
                    # Turn on
                    result = await manager.control_lights(room_id, True)
                    print(f"  Room {room_id} lights ON: {result}")
                    
                    await asyncio.sleep(1)
                    
                    # Turn off
                    result = await manager.control_lights(room_id, False)
                    print(f"  Room {room_id} lights OFF: {result}")
                
                print()
            
            if lock_endpoints:
                print(f"Found {len(lock_endpoints)} lock controls")
                
                for endpoint in lock_endpoints:
                    room_id = endpoint.split('/')[0]
                    
                    # Lock
                    result = await manager.control_lock(room_id, True)
                    print(f"  Room {room_id} LOCKED: {result}")
                    
                    await asyncio.sleep(2)
                    
                    # Unlock
                    result = await manager.control_lock(room_id, False)
                    print(f"  Room {room_id} UNLOCKED: {result}")
                    
                    await asyncio.sleep(1)
                    
                    # Get status
                    result = await manager.get_room_status(room_id)
                    print(f"  Room {room_id} status: {result}")
                
                print()
            
            if countdown_endpoints:
                print(f"Found {len(countdown_endpoints)} countdown timers")
                
                for endpoint in countdown_endpoints:
                    room_id = endpoint.split('/')[0]
                    
                    # Set countdown for 10 seconds
                    result = await manager.set_countdown(room_id, 10)
                    print(f"  Room {room_id} countdown set to 10s: {result}")
                    
                    await asyncio.sleep(3)
                    
                    # Check countdown status
                    result = await manager.get_countdown(room_id)
                    print(f"  Room {room_id} countdown status: {result}")
                
                print()
            
            await asyncio.sleep(10)
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
        manager.stop_discovery()
        await asyncio.sleep(1)
        print("Stopped.")

if __name__ == "__main__":
    asyncio.run(_demo())
