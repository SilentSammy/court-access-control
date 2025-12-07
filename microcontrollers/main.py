import asyncio
import time
from matrix_pad import MatrixPad
from display import Display
from lcd import LCD
from io_man import IOManager
from async_runner import start, stop, calculate_sleep_until
from machine import Timer

# System state management
is_idle = True           # Boolean: Are we in idle/screensaver state?
active_mode = "password"  # String: What mode to enter when NOT idle?
last_activity_time = 0   # Timestamp of last character received
idle_timeout = 10        # Seconds of inactivity before going idle

def wake_up():
    """Exit idle state and enter the active mode"""
    global is_idle, last_activity_time
    is_idle = False
    last_activity_time = time.time()

def go_idle():
    """Return to idle/screensaver state"""
    global is_idle
    is_idle = True

def set_mode(new_mode):
    """Change the active mode (what runs when not idle)"""
    global active_mode
    active_mode = new_mode
    io.interrupt()  # Wake up any blocking read_char calls

def on_char_received(char):
    """Callback for every character received - updates activity timestamp"""
    global last_activity_time
    last_activity_time = time.time()

def check_idle_timeout(timer):
    """Watchdog timer callback - automatically go idle after timeout"""
    global is_idle, last_activity_time
    if not is_idle and time.time() - last_activity_time > idle_timeout:
        go_idle()
        io.interrupt()  # Wake up any blocking read_char/read_input calls

lcd = LCD(E=16, RS=17, D7=18, D6=19, D5=20, D4=21)
display = Display(lcd.update_display)
pad = MatrixPad([2, 3, 4, 5], [6, 7, 8, 9])

# Create IOManager instance
io = IOManager(pad.read_char, display.overwrite)
io.on_char_received = on_char_received

# Set up watchdog timer to check for idle timeout
idle_watchdog = Timer()
idle_watchdog.init(period=1000, mode=Timer.PERIODIC, callback=check_idle_timeout)

async def locked_mode():
    """Security lock mode - only REPL can exit"""
    if active_mode != "locked":
        go_idle()  # Mode changed, return to idle
        return
    
    io.display("LOCKED!\nREPL only")
    try:
        await io.read_char(timeout=0.1)  # Check for interrupts
    except KeyboardInterrupt:
        pass  # Check mode again on next loop

async def password_mode():
    """Password entry mode"""
    try:
        password = await io.read_input("Password: {0}", max_length=4)
        
        # Check if we went idle during input (watchdog triggered)
        if is_idle:
            return  # Exit to main loop which will show clock
        
        if password == "1234":
            io.display("Access Granted!\nWelcome!")
            try:
                await io.read_char(timeout=2.0)  # Wait 2s or until interrupt
            except KeyboardInterrupt:
                pass
            io.display("System ready\nPress any key...")
            await io.read_char()
        else:
            io.display("Access Denied!\nTry again...")
            try:
                await io.read_char(timeout=2.0)  # Wait 2s or until interrupt
            except KeyboardInterrupt:
                pass
                
    except KeyboardInterrupt:
        pass  # Interrupted - will check mode/idle state on next loop
    
    # Return to idle if not already there
    if not is_idle:
        go_idle()

async def main():
    """Interactive time display - press any key to interrupt"""
    global is_idle, active_mode
    
    while True:
        if is_idle:
            # Idle state - display clock
            # Get current time and format as 24h
            now = time.localtime()
            time_str = f"{now[3]:02d}:{now[4]:02d}:{now[5]:02d}"
            date_str = f"{now[2]:02d}/{now[1]:02d}/{now[0]}"
            
            # Display time on line 1, date on line 2
            io.display(f"{time_str}\n{date_str}")
            
            try:
                sleep_duration = calculate_sleep_until(interval=1)
                char = await io.read_char(timeout=max(0.1, sleep_duration))
                
                if char is not None:
                    # User pressed a key - wake up and enter active mode
                    # Note: timestamp already updated by on_char_received callback
                    is_idle = False
                    io.push_char(char)
                    
            except KeyboardInterrupt:
                pass  # Mode might have changed, loop will check
                
        else:
            # Run the active mode
            if active_mode == "password":
                await password_mode()
                # password_mode() calls go_idle() when done
                
            elif active_mode == "locked":
                await locked_mode()
                # locked_mode() calls go_idle() when unlocked

# Auto-start if running as main program
if __name__ == "__main__":
    start(main)
else:
    # When imported, just make start() available
    print("Module loaded. Call start(main) to begin, stop() to end.")
