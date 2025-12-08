import asyncio
import time
from matrix_pad import MatrixPad
from display import Display
from lcd import LCD
from io_man import IOManager
from async_runner import start, stop, calculate_sleep_until
from machine import Timer
from hardware import set_lock, set_light, get_lock_state, get_light_state, check_unlock_button, quick_unlock


# System state management
active_mode = "idle"      # Current mode: "idle", "password", or "menu"
last_activity_time = 0    # Timestamp of last character received
idle_timeout = 10         # Seconds of inactivity before returning to idle

def set_mode(new_mode):
    """Change the active mode and interrupt any blocking I/O"""
    global active_mode
    active_mode = new_mode
    io.interrupt()  # Wake up any blocking read_char calls

def on_char_received(char):
    """Callback for every character received - updates activity timestamp"""
    global last_activity_time
    last_activity_time = time.time()

def check_idle_timeout(timer):
    """Watchdog timer callback - automatically return to idle after timeout"""
    global last_activity_time
    if active_mode != "idle" and time.time() - last_activity_time > idle_timeout:
        set_mode("idle")

lcd = LCD(E=16, RS=17, D7=18, D6=19, D5=20, D4=21)
display = Display(lcd.update_display)
pad = MatrixPad([2, 3, 4, 5], [6, 7, 8, 9])

# Create IOManager instance
io = IOManager(pad.read_char, display.overwrite)
io.on_char_received = on_char_received

# Set up watchdog timer to check for idle timeout
idle_watchdog = Timer()
idle_watchdog.init(period=1000, mode=Timer.PERIODIC, callback=check_idle_timeout)

async def idle_mode():
    """Idle mode - display clock and wait for keypress"""
    # Get current time and format as 24h
    now = time.localtime()
    time_str = f"{now[3]:02d}:{now[4]:02d}:{now[5]:02d}"
    date_str = f"{now[2]:02d}/{now[1]:02d}/{now[0]}"
    
    # Display time on line 1, date on line 2
    io.display(f"{time_str}\n{date_str}")
    
    sleep_duration = calculate_sleep_until(interval=1)
    char = await io.read_char(timeout=max(0.1, sleep_duration))
    
    if char is not None:
        # User pressed a key - transition to password mode
        io.push_char(char)
        set_mode("password")

async def password_mode():
    """Password entry mode"""
    password = await io.read_input("Password: {0}", max_length=4)
    
    # Check if mode changed during input (watchdog triggered)
    if active_mode != "password":
        return
    
    if password == "1234":
        io.display("Access Granted!\nWelcome!")
        await io.read_char(timeout=1.5)  # Brief welcome message
        # Transition to menu mode if not interrupted
        if active_mode == "password":
            set_mode("menu")
    else:
        io.display("Access Denied!\nTry again...")
        await io.read_char(timeout=2.0)  # Wait 2s or until interrupt
        if active_mode == "password":
            set_mode("idle")

async def menu_mode():
    """Main control menu - accessible after authentication"""
    index, choice = await io.prompt_menu("Main Menu", [
        "Toggle Door",
        "Toggle Light",
        "Quick Unlock"
    ], timeout=10)
    
    # Check if mode changed during menu (watchdog triggered)
    if active_mode != "menu":
        return
    
    # Execute selected action
    if index == 0:  # Toggle Door
        set_lock()
        state = "Locked" if get_lock_state() else "Unlocked"
        io.display(f"Door {state}!")
    
    elif index == 1:  # Toggle Light
        set_light()
        state = "On" if get_light_state() else "Off"
        io.display(f"Light {state}!")
    
    elif index == 2:  # Quick Unlock
        duration = quick_unlock(3)
        io.display(f"Unlocked for\n{duration} seconds")
    
    # Show result briefly, then return to idle
    await io.read_char(timeout=2.0)
    
    # Always return to idle after menu action
    if active_mode == "menu":
        set_mode("idle")

async def main():
    """Main event loop - runs current mode continuously"""
    while True:
        try:
            if active_mode == "idle":
                await idle_mode()
                
            elif active_mode == "password":
                await password_mode()
                
            elif active_mode == "menu":
                await menu_mode()
                
        except KeyboardInterrupt:
            # Interrupt cascaded from mode function (watchdog or user cancel)
            # Loop will check active_mode on next iteration
            pass

# Auto-start if running as main program
if __name__ == "__main__":
    start(main)
else:
    # When imported, just make start() available
    print("Module loaded. Call start(main) to begin, stop() to end.")
