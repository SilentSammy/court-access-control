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
    """Create a handler for a specific room's lights"""
    def handler(request):
        light = room_lights[room_num]
        state_param = request['params'].get('state')
        
        if state_param is None:
            # No state provided - toggle
            light.value(not light.value())
            action = "toggled"
        else:
            # Set to specific state
            state = int(state_param)
            light.value(state)
            action = "on" if state else "off"
        
        return {
            "room": room_num,
            "light": "on" if light.value() else "off",
            "action": action
        }
    return handler

# Build endpoints for all 3 rooms
endpoints = {
    "1/lights": handle_lights(1),
    "2/lights": handle_lights(2),
    "3/lights": handle_lights(3)
}

print("Connecting to WiFi...")
connect_wifi(wait=True)

if wlan.isconnected():
    ip = wlan.ifconfig()[0]
    print("\nRoom light controller ready. Endpoints:")
    print("  http://" + ip + "/1/lights?state=1  (turn on room 1)")
    print("  http://" + ip + "/1/lights?state=0  (turn off room 1)")
    print("  http://" + ip + "/1/lights          (toggle room 1)")
    print("  (Same for /2/lights and /3/lights)")
    print("\nPress Ctrl+C to stop server\n")
    start_webserver(endpoints)
else:
    print("WiFi not connected. Server not started.")
