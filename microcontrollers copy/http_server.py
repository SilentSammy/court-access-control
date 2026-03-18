import time
import ure
import ujson
import socket
import ntptime
import machine
import network

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
wlan = network.WLAN(network.STA_IF)

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

def connect_wifi(wait=True):
    with open("wifi.txt", "r") as file:
        ssid = file.readline().strip()
        password = file.readline().strip()
    wlan.active(True)
    wlan.connect(ssid, password)

    if wait:
        for i in range(10):
            if wlan.isconnected():
                break
            time.sleep(1)
        if wlan.isconnected():
            print("Connected to", wlan.config('ssid'), "with IP", wlan.ifconfig()[0])
        else:
            print("Failed to connect to", ssid)

def stop_webserver():
    """Stop the web server and clean up the socket"""
    global server_socket
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
                if isinstance(result, dict):
                    body = ujson.dumps(result)
                elif result is not None:
                    body = str(result)
                response = ("HTTP/1.1 200 OK\r\n"
                            "Access-Control-Allow-Origin: *\r\n"
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

if __name__ == "__main__":
    from machine import Pin
    
    # Set up room lights on pins 11, 12, 13
    room_lights = {
        1: Pin(11, Pin.OUT),
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
