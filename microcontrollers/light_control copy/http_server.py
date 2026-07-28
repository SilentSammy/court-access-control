import time
import ure
import ujson
import socket
import ntptime
import machine
import network
from machine import Timer, WDT

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
wlan = network.WLAN(network.STA_IF)

# === WATCHDOG TIMER SETUP ===
last_ping_time = None
wdt = None
wdt_timer = None
wdt_initialized = False
wdt_ping_timeout = 600  # seconds (10 minutes)
wdt_hwdt_timeout = 900000  # milliseconds (15 minutes)

def sync_time():
    try:
        ntptime.settime()
        print("Time synced")
    except OSError:
        print("Failed to sync time")

def start_access_point(pwd=""):
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    essid = 'MyESP_Hotspot'
    
    if pwd:
        # Protected access point with WPA/WPA2
        ap.config(essid=essid, password=pwd, authmode=network.AUTH_WPA_WPA2_PSK)
    else:
        # Open access point (no password)
        ap.config(essid=essid, authmode=network.AUTH_OPEN)
    
    print("Access Point started with IP:", ap.ifconfig()[0])

def connect_wifi(wait=True, max_retries=5):
    """Connect to WiFi with retry logic and initialization delay.
    
    Args:
        wait: If True, block until connected
        max_retries: Number of connection attempts before giving up
    """
    with open("wifi.txt", "r") as file:
        ssid = file.readline().strip()
        password = file.readline().strip()
    
    # Give WiFi radio time to initialize (common ESP32 issue)
    print("Initializing WiFi radio...")
    time.sleep(1)
    
    # Deactivate and reactivate to clear any stale state
    wlan.active(False)
    time.sleep(0.5)
    wlan.active(True)
    time.sleep(0.5)
    
    # Retry logic with exponential backoff
    for attempt in range(max_retries):
        try:
            print(f"WiFi connection attempt {attempt + 1}/{max_retries}...")
            wlan.connect(ssid, password)
            
            if wait:
                # Wait up to 20 seconds for connection
                for i in range(20):
                    if wlan.isconnected():
                        print("Connected to", wlan.config('ssid'), "with IP", wlan.ifconfig()[0])
                        return True
                    time.sleep(1)
                
                # Not connected yet, continue to retry
                print(f"Connection attempt {attempt + 1} timed out. Retrying...")
                wlan.disconnect()
                time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s, 8s, 16s
                
        except OSError as e:
            print(f"WiFi error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                raise
    
    if not wlan.isconnected():
        print(f"Failed to connect to {ssid} after {max_retries} attempts")
        return False
    
    return True

def init_watchdog(ping_timeout_seconds=600, hwdt_timeout_ms=900000):
    """Initialize the dual-layer watchdog system.
    
    Args:
        ping_timeout_seconds: App-level timeout (10 min = 600 sec)
        hwdt_timeout_ms: Hardware WDT timeout (15 min = 900000 ms)
    
    The watchdog works by:
    1. Hardware WDT (backstop): Triggers system reset if code truly freezes
    2. App-level watchdog: Monitors ping health and resets if no ping within timeout
    """
    global last_ping_time, wdt, wdt_timer, wdt_initialized
    global wdt_ping_timeout, wdt_hwdt_timeout
    
    wdt_ping_timeout = ping_timeout_seconds
    wdt_hwdt_timeout = hwdt_timeout_ms
    last_ping_time = time.time()
    
    try:
        # Initialize hardware watchdog (15 minutes)
        wdt = WDT(timeout=hwdt_timeout_ms)
        print(f"[WDT] Hardware watchdog initialized ({hwdt_timeout_ms}ms)")
    except Exception as e:
        print(f"[WDT] Warning: Could not initialize hardware WDT: {e}")
        wdt = None
    
    # Set up periodic watchdog check (every 60 seconds)
    wdt_timer = Timer(0)
    wdt_timer.init(period=60000, mode=Timer.PERIODIC, callback=_watchdog_check_callback)
    wdt_initialized = True
    print(f"[WDT] App-level watchdog initialized (ping timeout: {ping_timeout_seconds}s)")

def _watchdog_check_callback(timer):
    """Periodic callback to check watchdog health and feed hardware WDT."""
    global last_ping_time, wdt
    
    if not wdt_initialized or last_ping_time is None:
        return
    
    # Feed the hardware watchdog
    if wdt:
        try:
            wdt.feed()
        except Exception as e:
            print(f"[WDT] Error feeding hardware WDT: {e}")
    
    # Check if we've exceeded the app-level ping timeout
    time_since_ping = time.time() - last_ping_time
    
    if time_since_ping > wdt_ping_timeout:
        print(f"[WDT] TIMEOUT: No ping for {time_since_ping:.0f}s (limit: {wdt_ping_timeout}s)")
        print("[WDT] Triggering system reset...")
        machine.reset()

def stop_webserver():
    """Stop the web server and clean up the socket"""
    global server_socket, wdt_timer
    
    # Stop watchdog timer if running
    if wdt_timer:
        try:
            wdt_timer.deinit()
            wdt_timer = None
        except:
            pass
    
    if server_socket:
        try:
            server_socket.close()
            print("Web server stopped")
        except:
            pass
        server_socket = None

def start_webserver(endpoints):
    def handle_client(client_socket):
        # Set a timeout so we don't block indefinitely
        client_socket.settimeout(2)
        while True:
            try:
                data = client_socket.recv(1024)
                if not data:
                    break  # Client closed connection
            except OSError:
                break  # Timeout or socket error

            # Parse the HTTP request
            request = parse_http_request(data.decode())
            
            # Default response (404 Not Found with empty body)
            default_body = ""
            default_response = ("HTTP/1.1 404 Not Found\r\n"
                                "Connection: keep-alive\r\n"
                                "Content-Length: " + str(len(default_body)) + "\r\n\r\n" +
                                default_body)
            response = default_response

            # Check if endpoint exists in our endpoints dict
            endpoint = request['endpoint'].strip('/') if request['endpoint'] else ''
            if endpoint in endpoints:
                result = endpoints[endpoint](request)
                body = ""
                content_type = "text/plain"
                if isinstance(result, dict):
                    body = ujson.dumps(result)
                    content_type = "application/json"
                elif result is not None:
                    body = str(result)
                response = ("HTTP/1.1 200 OK\r\n"
                            "Access-Control-Allow-Origin: *\r\n"
                            "Content-Type: " + content_type + "\r\n"
                            "Connection: keep-alive\r\n"
                            "Content-Length: " + str(len(body)) + "\r\n\r\n" +
                            body)
            try:
                client_socket.send(response)
            except Exception:
                break  # Exit if sending fails
        client_socket.close()

    global server_socket
    
    # Clean up any existing socket first
    stop_webserver()
    
    # Create new socket with proper error handling
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind(('', 80))
        server_socket.listen(5)
        print("Web server started")
        
        while True:
            try:
                client_socket, addr = server_socket.accept()
                print("Client connected from", addr)
                handle_client(client_socket)
            except KeyboardInterrupt:
                print("\nKeyboard interrupt - stopping web server")
                stop_webserver()
                break
            except Exception as e:
                print("Error accepting connection:", e)
                
    except OSError as e:
        if e.args[0] == 112:  # EADDRINUSE
            print("Port 80 is busy. Try: web.stop_webserver() then restart")
        else:
            print(f"Socket error: {e}")
        stop_webserver()

def get_watchdog_status(request):
    """Return current watchdog status. Read-only (doesn't reset timer)."""
    global last_ping_time
    
    if not wdt_initialized:
        return {"error": "Watchdog not initialized"}
    
    time_since_ping = time.time() - last_ping_time if last_ping_time else None
    
    return {
        "watchdog_enabled": wdt_initialized,
        "hardware_wdt_enabled": wdt is not None,
        "app_ping_timeout_s": wdt_ping_timeout,
        "hardware_wdt_timeout_ms": wdt_hwdt_timeout,
        "time_since_last_ping_s": time_since_ping,
        "status": "healthy" if time_since_ping and time_since_ping < wdt_ping_timeout else "warning"
    }

def parse_http_request(http_request):
    # Split request into headers and body
    parts = http_request.split('\n\n', 1)
    headers = parts[0]
    body = parts[1] if len(parts) > 1 else ''

    # Use regex to extract method, endpoint, and parameters
    method_match = ure.search(r'^(\w+)', headers)
    endpoint_match = ure.search(r'^\w+\s+([^?\s]+)', headers)
    params_match = ure.search(r'\?([^?\s]+)\s', headers)

    params_string = params_match.group(1) if params_match else None
    params = {}
    if params_string:
        for param in params_string.split('&'):
            key, value = param.split('=')
            params[key] = value

    result = {
        'method': method_match.group(1) if method_match else None,
        'endpoint': endpoint_match.group(1) if endpoint_match else None,
        'params': params,
        'body': body if body != '' else None
    }
    return result

def demo():
    def hello_endpoint(request):
        return {"message": "Hello, World!"}

    endpoints = {
        'hello': hello_endpoint
    }

    connect_wifi()
    sync_time()
    start_webserver(endpoints)

if __name__ == "__main__":
    demo()
