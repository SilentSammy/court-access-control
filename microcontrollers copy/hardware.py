from machine import Pin, Timer
import time

# Pin definitions
lock = Pin(12, Pin.OUT)
light = Pin(13, Pin.OUT)
unlock_button = Pin(14, Pin.IN, Pin.PULL_DOWN)

# State tracking
timestamps = {}
_quick_unlock_timer = Timer()

# Initialize to safe defaults
lock.on()   # Locked by default
light.off() # Light off by default

def set_lock(state=None):
    """
    Set lock state.
    
    Args:
        state: True to lock, False to unlock, None to toggle
    """
    _quick_unlock_timer.deinit()  # Cancel any quick unlock timer
    if state is None:
        state = not get_lock_state()
    lock.value(1 if state else 0)
    timestamps['lock'] = time.time()

def set_light(state=None):
    """
    Set light state.
    
    Args:
        state: True for on, False for off, None to toggle
    """
    if state is None:
        state = not get_light_state()
    light.value(1 if state else 0)
    timestamps['light'] = time.time()

def get_lock_state():
    """Returns True if locked, False if unlocked"""
    return bool(lock.value())

def get_light_state():
    """Returns True if light is on, False if off"""
    return bool(light.value())

def check_unlock_button():
    """Returns True if unlock button is currently pressed"""
    return bool(unlock_button.value())

def quick_unlock(seconds=3):
    """
    Unlock for a specified duration, then automatically relock.
    
    Args:
        seconds: Duration to keep unlocked (default 3 seconds)
        
    Returns:
        Number of seconds the door will remain unlocked
    """
    def relock(timer):
        set_lock(True)
    
    _quick_unlock_timer.deinit()  # Cancel previous timer if any
    set_lock(False)  # Unlock
    _quick_unlock_timer.init(
        period=int(seconds * 1000), 
        mode=Timer.ONE_SHOT, 
        callback=relock
    )
    return seconds

def cleanup():
    """Cleanup function to deinit timers"""
    _quick_unlock_timer.deinit()
