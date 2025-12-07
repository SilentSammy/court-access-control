import time
import asyncio

def calculate_sleep_until(interval, offset=0):
    """Calculate sleep duration until next interval boundary"""
    now = time.time()
    target = ((now - offset) // interval + 1) * interval + offset
    return target - now

async def no_drift_sleep(interval, offset=0):
    """Sleep until next interval boundary to prevent time drift"""
    sleep_duration = calculate_sleep_until(interval, offset)
    await asyncio.sleep(sleep_duration)

# Setup for REPL-compatible execution
_task = None
_timer = None

def start(main_func):
    """
    Start an async function in the background, keeping REPL active.
    
    Args:
        main_func: Async function to run (e.g., your main() coroutine)
    
    Returns:
        The created task
    """
    global _task, _timer
    
    from machine import Timer
    import uasyncio
    
    # Create the main task
    _task = uasyncio.create_task(main_func())
    
    # Use a timer to pump the event loop
    _timer = Timer()
    
    async def tick_async():
        # Yield control to allow tasks to run
        await uasyncio.sleep_ms(0)
    
    def tick(t):
        try:
            # Run a tiny async task to keep the loop going
            uasyncio.run(tick_async())
        except Exception as e:
            pass  # Silently ignore errors to keep timer running
    
    _timer.init(period=10, mode=Timer.PERIODIC, callback=tick)
    
    print("Application started in background. REPL is active!")
    return _task

def stop():
    """Stop the running application"""
    global _task, _timer
    if _task:
        _task.cancel()
        print("Application task stopped")
    if _timer:
        _timer.deinit()
        print("Timer stopped")
