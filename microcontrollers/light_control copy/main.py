from http_server import *

from machine import Pin
    
# Set up room lights on pins 14, 13, 12 (ACTIVE LOW)
room_lights = {
    1: Pin(14, Pin.OUT),
    2: Pin(12, Pin.OUT),
    3: Pin(13, Pin.OUT)
}

# Initialize all lights to off (HIGH for active low)
for light in room_lights.values():
    light.on()  # Active low: HIGH = OFF

def handle_lights(room_num):
    """Handle light operations for a specific room via query params.
    
    Query params:
        - No params: Get status (read-only)
        - state=1: Turn ON
        - state=0: Turn OFF
        - toggle=1: Toggle
    
    Note: Lights are ACTIVE LOW (pin LOW = light ON)
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
            light.value(not state)  # Invert for active low
            action = "on" if state else "off"
        # Default: just get status (no side effects)
        else:
            action = "status"
        
        return {
            "room": room_num,
            "light": "on" if not light.value() else "off",  # Invert for active low
            "action": action
        }
    return handler

def device_info_handler(request):
    """Return device information for discovery.
    
    Also resets the watchdog timer since this endpoint is pinged by the central server.
    """
    global last_ping_time
    last_ping_time = time.time()  # Reset watchdog timer
    
    return {
        "device_type": "light_controller",
        "endpoints": ["1/lights", "2/lights", "3/lights", "watchdog-status"]
    }

# Build endpoints for all 3 rooms
endpoints = {
    "device-info": device_info_handler,
    "watchdog-status": get_watchdog_status,
    "1/lights": handle_lights(1),
    "2/lights": handle_lights(2),
    "3/lights": handle_lights(3)
}

print("Connecting to WiFi...")
if not connect_wifi(wait=True, max_retries=5):
    print("ERROR: WiFi connection failed. Device will not start.")
    print("Check wifi.txt credentials and network availability.")
    import sys
    sys.exit(1)

if wlan.isconnected():
    ip = wlan.ifconfig()[0]
    
    # Initialize watchdog (app-level: 10 min, hardware: 15 min)
    init_watchdog(ping_timeout_seconds=600, hwdt_timeout_ms=900000)
    
    print("\n" + "="*60)
    print("Room light controller ready!")
    print("="*60)
    print("\n📡 Core Endpoints:")
    print("  http://" + ip + "/device-info              (device discovery - resets watchdog)")
    print("  http://" + ip + "/watchdog-status          (view watchdog health)")
    print("\n💡 Light Control Endpoints:")
    print("  http://" + ip + "/1/lights                 (get status room 1)")
    print("  http://" + ip + "/1/lights?state=1         (turn ON room 1)")
    print("  http://" + ip + "/1/lights?state=0         (turn OFF room 1)")
    print("  http://" + ip + "/1/lights?toggle=1        (toggle room 1)")
    print("  (Same for /2/lights and /3/lights)")
    print("\n🔒 Watchdog Protection:")
    print("  • Hardware WDT: 15 minutes (system freeze backstop)")
    print("  • App-level WDT: 10 minutes (network/ping monitoring)")
    print("  • Server must call /device-info regularly to prevent reset")
    print("\nPress Ctrl+C to stop server\n")
    print("="*60 + "\n")
    start_webserver(endpoints)
else:
    print("WiFi not connected. Server not started.")
