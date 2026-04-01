from http_server import *

from machine import Pin
    
# Set up room lights on pins 14, 13, 12
room_lights = {
    1: Pin(14, Pin.OUT),
    2: Pin(12, Pin.OUT),
    3: Pin(13, Pin.OUT)
}

# Initialize all lights to off
for light in room_lights.values():
    light.off()

def handle_lights(room_num):
    """Handle light operations for a specific room via query params.
    
    Query params:
        - No params: Get status (read-only)
        - state=1: Turn ON
        - state=0: Turn OFF
        - toggle=1: Toggle
    """
    def handler(request):
        light = room_lights[room_num]
        params = request.get('params', {})
        
        # Check for toggle request
        if params.get('toggle'):
            light.value(not light.value())
            action = "toggled"
        # Check for state change request
        elif 'state' in params:
            state = int(params['state'])
            light.value(state)
            action = "on" if state else "off"
        # Default: just get status (no side effects)
        else:
            action = "status"
        
        return {
            "room": room_num,
            "light": "on" if light.value() else "off",
            "action": action
        }
    return handler

def device_info_handler(request):
    """Return device information for discovery"""
    return {
        "device_type": "light_controller",
        "endpoints": ["1/lights", "2/lights", "3/lights"]
    }

# Build endpoints for all 3 rooms
endpoints = {
    "device-info": device_info_handler,
    "1/lights": handle_lights(1),
    "2/lights": handle_lights(2),
    "3/lights": handle_lights(3)
}

print("Connecting to WiFi...")
connect_wifi(wait=True)

if wlan.isconnected():
    ip = wlan.ifconfig()[0]
    print("\nRoom light controller ready. Endpoints:")
    print("  http://" + ip + "/device-info        (get device info for discovery)")
    print("  http://" + ip + "/1/lights           (get status room 1)")
    print("  http://" + ip + "/1/lights?state=1   (turn on room 1)")
    print("  http://" + ip + "/1/lights?state=0   (turn off room 1)")
    print("  http://" + ip + "/1/lights?toggle=1  (toggle room 1)")
    print("  (Same for /2/lights and /3/lights)")
    print("\nPress Ctrl+C to stop server\n")
    start_webserver(endpoints)
else:
    print("WiFi not connected. Server not started.")
