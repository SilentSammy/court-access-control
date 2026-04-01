from http_server import *
from machine import Pin, Timer
from display import HT16K33Display, I2C

# === CONFIGURATION ===
ROOM = 1  # Change this for different rooms

# === HARDWARE SETUP ===
# Initialize I2C and display (Raspberry Pi Pico W: GP21=SCL, GP20=SDA)
i2c = I2C(0, scl=Pin(21), sda=Pin(20), freq=400000)
display = HT16K33Display(i2c)

# Initialize relay for maglock (GP22)
# Relay logic: HIGH = locked, LOW = unlocked (adjust if needed)
relay = Pin(22, Pin.OUT)
relay.value(0)  # Start unlocked

# Initialize pushbutton for safety unlock (GP19)
button = Pin(19, Pin.IN, Pin.PULL_UP)  # Active low (pressed = 0)

# === PRIORITY DISPLAY SYSTEM ===
# Lower number = higher priority (0 is highest)
display_messages = {
    3: "00:00"  # Countdown (idle message, lowest priority)
}
display_clear_timers = {}  # Timers for auto-clearing messages

def set_display(text, priority=2, duration=None):
    """Set a display message at a given priority level.
    
    Priority levels (lower = higher priority):
        0: Critical system messages
        1: Lock state changes
        2: Temporary messages (default)
        3: Idle/countdown state
    
    Args:
        text: Text to display
        priority: Priority level (0-3)
        duration: Optional duration in milliseconds before auto-clearing
    """
    display_messages[priority] = text
    
    # Cancel any existing clear timer for this priority
    if priority in display_clear_timers:
        display_clear_timers[priority].deinit()
        del display_clear_timers[priority]
    
    # Set up auto-clear timer if duration specified
    if duration is not None:
        timer = Timer(-1)
        timer.init(period=duration, mode=Timer.ONE_SHOT, 
                  callback=lambda t: clear_display(priority))
        display_clear_timers[priority] = timer

def clear_display(priority):
    """Clear a display message at a given priority level."""
    if priority in display_messages:
        del display_messages[priority]
    if priority in display_clear_timers:
        display_clear_timers[priority].deinit()
        del display_clear_timers[priority]

def update_display(timer):
    """Update the physical display with the highest priority message."""
    if display_messages:
        # Get the message with the lowest priority number (highest priority)
        highest_priority = min(display_messages.keys())
        display.display_string(display_messages[highest_priority])

# Start display update timer (refresh every 100ms)
display_timer = Timer(-1)
display_timer.init(period=100, mode=Timer.PERIODIC, callback=update_display)

# === COUNTDOWN SYSTEM ===
import time
countdown_end = 0  # Unix timestamp when countdown reaches 00:00

def update_countdown(timer):
    """Update the countdown display based on time remaining."""
    global countdown_end
    
    if countdown_end == 0:
        # No countdown active, show 00:00
        set_display("00:00", priority=3)
        return
    
    # Calculate time remaining
    now = time.time()
    remaining = countdown_end - now
    
    if remaining <= 0:
        # Countdown finished, show 00:00
        set_display("00:00", priority=3)
        return
    
    # Convert to minutes and seconds
    total_seconds = int(remaining)
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    
    # Cap at 99:59
    if minutes > 99:
        minutes = 99
        seconds = 59
    
    # Format as MM:SS
    time_str = "{:02d}:{:02d}".format(minutes, seconds)
    set_display(time_str, priority=3)

# Start countdown update timer (refresh every second)
countdown_timer = Timer(-1)
countdown_timer.init(period=1000, mode=Timer.PERIODIC, callback=update_countdown)

# === SAFETY UNLOCK SYSTEM ===
relock_timer = Timer(-1)  # Timer for auto re-locking

def quick_unlock(duration=5000):
    """Unlock the door temporarily. Spammable - resets timer each call.
    
    Args:
        duration: Duration in milliseconds to stay unlocked (default: 5000ms = 5s)
    """
    global relock_timer
    
    # Unlock the door
    relay.value(0)
    set_display("OPEN", priority=1, duration=2000)
    print("QUICK UNLOCK")
    
    # Cancel any existing relock timer and start a new one
    relock_timer.deinit()
    relock_timer.init(period=duration, mode=Timer.ONE_SHOT, callback=relock)

def relock(timer):
    """Re-lock the door after temporary unlock."""
    relay.value(1)
    set_display("LOCK", priority=1, duration=2000)

def check_button(timer):
    """Periodically check if safety button is pressed."""
    if button.value() == 0:  # Button pressed (active low)
        quick_unlock()

# Start button monitor timer (check every 100ms)
button_timer = Timer(-1)
button_timer.init(period=100, mode=Timer.PERIODIC, callback=check_button)

def handle_lock(request):
    """Handle lock operations via query params.
    
    Query params:
        - No params: Get status (read-only)
        - state=1: Lock
        - state=0: Unlock
    """
    params = request.get('params', {})
    
    # Check for state change request
    if 'state' in params:
        state = int(params['state'])
        relay.value(state)
        action = "locked" if state else "unlocked"
        
        # Update display
        if state:
            set_display("LOCK", priority=1, duration=2000)
        else:
            set_display("OPEN", priority=1, duration=2000)
    else:
        # Just get status (no side effects)
        action = "status"
    
    return {
        "room": ROOM,
        "lock": "locked" if relay.value() else "unlocked",
        "action": action
    }

def handle_countdown(request):
    """Handle countdown timer operations.
    
    Query params:
        - s=<seconds>: Set countdown for <seconds> into the future
        - No params: Get current countdown status
    """
    global countdown_end
    import time
    
    params = request.get('params', {})
    
    if 's' in params:
        # Set new countdown
        seconds = int(params['s'])
        countdown_end = time.time() + seconds
        action = "set"
    else:
        # Just get status
        action = "status"
    
    # Calculate remaining time for response
    now = time.time()
    remaining = max(0, int(countdown_end - now)) if countdown_end > 0 else 0
    
    return {
        "room": ROOM,
        "countdown_remaining": remaining,
        "action": action
    }

def device_info_handler(request):
    """Return device information for discovery"""
    return {
        "device_type": "access_controller",
        "endpoints": [f"{ROOM}/lock", f"{ROOM}/countdown"]
    }

# Build endpoints
endpoints = {
    "device-info": device_info_handler,
    f"{ROOM}/lock": handle_lock,
    f"{ROOM}/countdown": handle_countdown
}

print("Connecting to WiFi...")
connect_wifi(wait=True)

if wlan.isconnected():
    ip = wlan.ifconfig()[0]
    print(f"\nRoom {ROOM} access controller ready at:", ip)
    print("Endpoints:")
    print("  http://" + ip + "/device-info        (get device info)")
    print("  http://" + ip + f"/{ROOM}/lock           (get lock status)")
    print("  http://" + ip + f"/{ROOM}/lock?state=1   (lock)")
    print("  http://" + ip + f"/{ROOM}/lock?state=0   (unlock)")
    print("  http://" + ip + f"/{ROOM}/countdown      (get countdown status)")
    print("  http://" + ip + f"/{ROOM}/countdown?s=60 (set 60s countdown)")
    print("\nPress Ctrl+C to stop server\n")
    start_webserver(endpoints)
else:
    print("WiFi not connected. Server not started.")
