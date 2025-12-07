from machine import Timer
import machine
import utime
import web
from matrix_pad import MatrixPad
from display import Display
from lcd import LCD

if machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_DOWN).value() == 1:
    raise SystemExit # if GP0 is high, exit the program

TZ_OFFSET = -6
START = utime.ticks_ms()
with open("id.txt", "r") as file:
    DEVICE_ID = file.readline().strip()
    DEVICE_NAME = file.readline().strip()
    PASS = file.readline().strip()
lcd = LCD(E=16, RS=17, D7=18, D6=19, D5=20, D4=21)
display = Display(lcd.update_display)
door_sensor = machine.Pin(14, machine.Pin.IN, machine.Pin.PULL_DOWN)
unlock = machine.Pin(22, machine.Pin.OUT)
dark = machine.Pin(26, machine.Pin.OUT)
unlock.off() # door locked by default
dark.on() # light off by default
timestamps = {}
timers = {}
with open("index.html", "r") as file:
    html = file.read()

def get_time():
    return utime.time() + 3600 * TZ_OFFSET

def format_timestamp(timestamp, format_string="{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}"):
    time_tuple = utime.localtime(timestamp)
    return format_string.format(
        year=time_tuple[0],
        month=time_tuple[1],
        day=time_tuple[2],
        hour=time_tuple[3],
        minute=time_tuple[4],
        second=time_tuple[5]
    )

def alternate_strings(strFuncs, duration):
    """This function will choose a string from a list based on the current time."""
    
    current_time = utime.time()
    index = (current_time // duration) % len(strFuncs)
    return strFuncs[index]()

def change_lock_state(state):
    timers.setdefault('lock', Timer()).deinit() # Cancel quick unlock timer
    if unlock.value() == state:
        unlock.value(state ^ 1)
        timestamps['lock'] = utime.ticks_ms()
    display.overwrite("Locked" if state else "Unlocked", 1, 2)
    return unlock.value() ^ 1

def quick_unlock(seconds=3):
    def end(timer):
        unlock.off()
        timestamps['lock'] = utime.ticks_ms()
        display.overwrite("Locked", 1, 2)
    timers.setdefault('lock', Timer()).deinit()  # Cancel the previous timer
    unlock.on()
    timestamps['lock'] = utime.ticks_ms()
    display.overwrite("Unlocked", 1)
    timers['lock'].init(period=int(seconds * 1000), mode=machine.Timer.ONE_SHOT, callback=end)
    return seconds

def change_light_state(state):
    if dark.value() == state:
        dark.value(state ^ 1)
        timestamps['light'] = utime.ticks_ms()
    return dark.value() ^ 1

def init_pass_input():
    passcode = PASS
    input = ""
    pad = MatrixPad([2, 3, 4, 5], [6, 7, 8, 9])
    clear_timer = Timer()

    def loop(timer):
        nonlocal input

        def clear(timer):
            nonlocal input
            display.clear(2)
            input = ""

        # check for input
        key = pad.check_key_press()
        if key is not None:
            # reset the timer
            clear_timer.deinit()
            clear_timer.init(period=5000, mode=Timer.ONE_SHOT, callback=clear)

            # add the input to the passcode
            char = pad.get_char(key)
            input += char

            # if the input is the same length as the passcode, check if it's correct
            if len(input) == len(passcode):
                accept_passcode()
            else:
                display.overwrite("Pass: " + input, 2)
    
    def accept_passcode(in_pass=None):
        nonlocal input
        print("Checking passcode", in_pass or input)
        result = (in_pass or input) == passcode
        if result:
            print("Correct passcode")
            display.clear(2)
            start_session()
        else:
            print("Wrong passcode")
            display.overwrite("Wrong passcode", 2, 2)
        input = ""
        return result

    timers.setdefault('pass', Timer()).init(period=100, mode=machine.Timer.PERIODIC, callback=loop)
    return accept_passcode

def init_unlocker_btn():
    open_button = machine.Pin(15, machine.Pin.IN, machine.Pin.PULL_DOWN)
    def loop(timer):
        if open_button.value():
            quick_unlock()
    timers.setdefault('btn', Timer()).init(period=100, mode=machine.Timer.PERIODIC, callback=loop)

def init_bg_display(strFuncs=None, duration=4):
    debug_pin = machine.Pin(1, machine.Pin.IN, machine.Pin.PULL_DOWN)
    
    if strFuncs is None:
        strFuncs = [
            lambda: "Welcome to\nPlayPass Courts!",
            lambda: "Room: " + DEVICE_ID + "\n" + DEVICE_NAME,
            lambda: "Date: {:02d}-{:02d}-{:02d}\nTime: {:02d}:{:02d}:{:02d}".format(*utime.localtime(get_time())),
        ]
        debug_strs = [
            lambda: web.wlan.config('ssid') + "\n" + web.wlan.ifconfig()[0],
            lambda: "STRT " + str(START) + "\nRUNT " + str(utime.ticks_ms() - START),
        ]

    def loop(timer):
        # if the debug pin is high, append the debug strings to the list of strings
        strs = strFuncs + debug_strs if debug_pin.value() else strFuncs
        
        # alternate between the strings
        display.overwrite(alternate_strings(strs, duration), -1)

        # calculate the time until the next second, and reset the timer
        time_until_next_second = 1000 - (utime.ticks_ms() % 1000)
        timer.init(period=time_until_next_second, mode=machine.Timer.ONE_SHOT, callback=loop)
    
    # start the timer
    loop(timers.setdefault('time', Timer()))

def init_sensors():
    door_prev = door_sensor.value()
    def loop(timer):
        nonlocal door_prev

        if door_sensor.value() != door_prev:
            door_prev = door_sensor.value()
            timestamps['door'] = utime.ticks_ms()
            display.overwrite("Door: " + ("Closed" if door_prev else "Opened"), 1, 2)
            
    timers.setdefault('sensors', Timer()).init(period=100, mode=machine.Timer.PERIODIC, callback=loop)

def start_session(duration=90):
    start = utime.ticks_ms()
    end = start + duration * 1000
    session_text = "{:02d}:{:02d} - {:02d}:{:02d}".format(*utime.localtime(get_time())[3:5], *utime.localtime(get_time() + duration)[3:5])
    def loop(timer):
        nonlocal session_text, end
        # display the time remaining in minutes and seconds
        now = utime.ticks_ms()
        remaining = utime.ticks_diff(end, now)
        display.overwrite(session_text + "\nLeft: {:02d}:{:02d}".format(int(remaining / 1000 / 60), int(remaining / 1000 % 60)), 0, 2)

        # calculate the time until the next second
        time_until_next_second = 1000 - (utime.ticks_ms() % 1000)

        # if session hasn't ended, reset the timer
        if remaining > 0:
            timer.init(period=time_until_next_second, mode=machine.Timer.ONE_SHOT, callback=loop)
        else:
            end_session()
    
    def end_session():
        change_light_state(False) # turn off the light
        change_lock_state(True) # lock the door
        display.overwrite("Session ended", 2, 2)
    
    # start the session
    display.overwrite("Session started", 2, 1)
    change_light_state(True) # turn on the light
    change_lock_state(False) # unlock the door
    # quick_unlock() # unlock the door

    # start the timer
    tmr = timers.setdefault('session', Timer())
    tmr.deinit()
    loop(tmr)

def get_status():
    status = {
        "device_id": DEVICE_ID,
        "device_name": DEVICE_NAME,
        "uptime_ms": utime.ticks_ms(),
        "time": format_timestamp(get_time()),
        "locked": { "state": unlock.value() ^ 1, "since_ms": timestamps.get('lock', START) },
        "light": { "state": dark.value() ^ 1, "since_ms": timestamps.get('light', START) },
        "door": { "state": door_sensor.value(), "since_ms": timestamps.get('door', START) }
    }
    return status

def deinit_timers():
    # deinit all timers
    print("Deinitializing timers:", ", ".join(timers.keys()))
    for timer in timers.values():
        timer.deinit()

def main():
    try:
        # init all timers
        pass_func = init_pass_input()
        # init_debug_display()
        init_unlocker_btn()
        init_sensors()
        init_bg_display()
        print("Program started")
        
        # start webserver
        endpoints = {
            "": lambda r: html,
            "quick_unlock": lambda r: quick_unlock(float(r['params'].get('dur', 3))),
            "lock": lambda r: change_lock_state(int(r['params'].get('state', unlock.value()))),
            "light": lambda r: change_light_state(int(r['params'].get('state', dark.value()))),
            "status": lambda r: get_status(),
            "passcode": lambda r: pass_func(r['params'].get('code', None)),
            "start_session": lambda r: start_session(int(r['params'].get('dur', 60))),
        }
        web.connect_wifi()
        web.start_webserver(endpoints)

        while True:
            pass
    finally:
        deinit_timers()
        web.server_socket.close()
        print("Program ended...")

if __name__ == "__main__":
    main()
else:
    main()