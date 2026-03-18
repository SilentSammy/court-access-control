# EXAMPLES
#   http://192.168.137.133/1/lights?state=1  (turn on room 1)
#   http://192.168.137.133/1/lights?state=0  (turn off room 1)
#   http://192.168.137.133/1/lights          (toggle room 1)
#   (Same for /2/lights and /3/lights)

import asyncio
import aiohttp
import json
import os

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
    except Exception as e:
        return f"Error: {str(e)}"

class FacilityManager:
    """Manages IoT devices across the entire facility."""
    
    def __init__(self, config_file=None, mock=True):
        """Initialize with room configuration.
        
        Args:
            config_file: Path to JSON configuration file
            mock: If True, methods return mock data without making HTTP requests (default: True)
        """
        self.config_file = config_file or os.path.join(
            os.path.dirname(__file__), 
            'facility_config.json'
        )
        self.mock = mock
        self.rooms = {}
        self._load_config()
    
    def _load_config(self):
        """Load room configuration from JSON file."""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.rooms = config.get('rooms', {})
        except FileNotFoundError:
            print(f"Config file not found: {self.config_file}")
            self.rooms = {
                "1": {"lights": "http://192.168.137.133/1/lights"},
                "2": {"lights": "http://192.168.137.133/2/lights"},
                "3": {"lights": "http://192.168.137.133/3/lights"}
            }
        except json.JSONDecodeError as e:
            print(f"Error parsing config file: {e}")
            self.rooms = {}
    
    def reload_config(self):
        """Reload configuration from file (allows runtime updates)."""
        self._load_config()
        return self.rooms
    
    async def control_lights(self, room_id, state):
        """Control room lights by ID.
        
        Args:
            room_id: Room identifier (string)
            state: True to turn on, False to turn off
        """
        # Reload config to support runtime changes
        self.reload_config()
        
        if room_id not in self.rooms:
            return {"error": f"Room {room_id} not found"}
        
        # TODO: Implement real HTTP communication with MCU
        # For now, always return mock response
        return {
            "room": int(room_id),
            "light": "on" if state else "off",
            "action": "on" if state else "off"
        }
    
    async def get_room_status(self, room_id):
        """Get the current status of a room by ID.
        
        Args:
            room_id: Room identifier (string)
        """
        # Reload config to support runtime changes
        self.reload_config()
        
        if room_id not in self.rooms:
            return {"error": f"Room {room_id} not found"}
        
        # TODO: Implement real HTTP communication with MCU
        # For now, always return mock response
        return {
            "room": int(room_id),
            "light": "on",
            "action": "toggled"
        }

async def _demo():
    """Demo showing FacilityManager usage."""
    manager = FacilityManager()
    
    print(f"Loaded {len(manager.rooms)} rooms from config")
    
    for i in range(2):
        print(f"\n--- Cycle {i+1} ---")
        
        print("Turning ON all lights...")
        for room_id in manager.rooms.keys():
            result = await manager.control_lights(room_id, True)
            print(f"  Room {room_id}: {result}")
        
        print("Turning OFF all lights...")
        for room_id in manager.rooms.keys():
            result = await manager.control_lights(room_id, False)
            print(f"  Room {room_id}: {result}")
        
        print("\nChecking room statuses...")
        for room_id in manager.rooms.keys():
            status = await manager.get_room_status(room_id)
            print(f"  Room {room_id}: {status}")

if __name__ == "__main__":
    asyncio.run(_demo())
