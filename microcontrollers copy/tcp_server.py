import socket
import sys
import network
import _thread
import time

command_map = {}
_tcp_sock = None
_tcp_conn = None
_tcp_addr = None
_tcp_buffer = b''
_tcp_running = False

def connect_wifi(ssid, password, wait=True):
	"""
	Connect to WiFi using provided ssid and password. Optionally wait for connection.
	"""
	wlan = network.WLAN(network.STA_IF)
	wlan.active(True)
	wlan.connect(ssid, password)
	if wait:
		for _ in range(20):
			if wlan.isconnected():
				break
			time.sleep(0.5)
		if wlan.isconnected():
			print("Connected to", ssid, "with IP", wlan.ifconfig()[0])
		else:
			print("Failed to connect to", ssid)
	return wlan

def connect_to_wifi_from_file(config_file="wifi.txt"):
	"""
	Connect to WiFi using credentials from a config file.
	"""
	with open(config_file, "r") as f:
		ssid = f.readline().strip()
		password = f.readline().strip()
	return connect_wifi(ssid, password)

def start(port=12345):
	"""
	Starts the TCP server in a background thread. Uses global command_map.
	"""
	global _tcp_sock, _tcp_running
	if _tcp_running:
		return
	_tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	_tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	_tcp_sock.bind(('', port))
	_tcp_sock.listen(1)
	_tcp_sock.setblocking(False)
	_tcp_running = True
	print('TCP server listening on port', port)
	def _loop():
		global _tcp_running
		while _tcp_running:
			try:
				_tcp_poll()
			except:
				pass  # Silently ignore all errors to prevent TinyUSB recursion
			time.sleep(0.05)
	_thread.start_new_thread(_loop, ())

def stop():
	"""
	Stops the TCP server and closes sockets.
	"""
	global _tcp_running, _tcp_sock, _tcp_conn
	_tcp_running = False
	if _tcp_conn:
		_tcp_conn.close()
		_tcp_conn = None
	if _tcp_sock:
		_tcp_sock.close()
		_tcp_sock = None
	print('TCP server stopped.')

def _tcp_poll():
	global _tcp_sock, _tcp_conn, _tcp_addr, _tcp_buffer, _tcp_running
	# Accept new connection if none
	if _tcp_conn is None:
		try:
			conn, addr = _tcp_sock.accept()
			conn.setblocking(False)
			_tcp_conn = conn
			_tcp_addr = addr
			_tcp_buffer = b''
			# print('Client connected from', addr)  # Removed: causes TinyUSB recursion
		except OSError:
			pass  # No connection yet
	# Handle data from client
	if _tcp_conn:
		try:
			data = _tcp_conn.recv(1024)
			if data:
				_tcp_buffer += data
				# Process lines
				while b'\n' in _tcp_buffer:
					line, _tcp_buffer = _tcp_buffer.split(b'\n', 1)
					line = line.decode().strip()
					# print('Received:', line)  # Removed: causes TinyUSB recursion
					if not line:
						_tcp_conn.send(b'EMPTY\n')
						continue
					cmd, args = parse_command_line(line)
					resp = execute_command(cmd, args, command_map)
					_tcp_conn.send((resp + '\n').encode())
			else:
				# Connection closed by client
				_tcp_conn.close()
				# print('Client disconnected')  # Removed: causes TinyUSB recursion
				_tcp_conn = None
				_tcp_addr = None
				_tcp_buffer = b''
		except OSError:
			pass  # No data available

def execute_command(cmd, args, command_map):
	"""
	Executes the command using the command_map. Returns response string.
	"""
	if cmd is None:
		return 'ERR: Invalid command'
	handler = command_map.get(cmd)
	if handler:
		try:
			resp = handler(args)
			if resp is None:
				resp = 'OK'
			return str(resp)
		except Exception as e:
			return 'ERR: ' + str(e)
	else:
		return 'UNKNOWN CMD'

def parse_command_line(line):
	"""
	Parse a command line in the format CMD:arg1,arg2,...
	Returns (cmd, args) where cmd is uppercase and args is a list of strings.
	"""
	line = line.strip()
	colon_idx = line.find(':')
	if colon_idx < 0:
		cmd = line.upper()
		args = []
	elif colon_idx == 0:
		return None, None  # Invalid command
	else:
		cmd = line[:colon_idx].strip().upper()
		arg_str = line[colon_idx+1:].strip()
		if not arg_str:
			args = []
		else:
			args = [a.strip() for a in arg_str.split(',') if a.strip()]
	return cmd, args

if __name__ == "__main__":
    import machine

    led = machine.Pin("LED", machine.Pin.OUT)

    def handle_led(args):
        if not args:
            return 'ERR: No value'
        try:
            val = int(args[0])
            led.value(1 if val else 0)
            return f'LED set to {val}'
        except Exception as e:
            return f'ERR: {e}'

    connect_wifi("SammyPC", "12345678")
    command_map = {
        'LED': handle_led,
    }

    # To start the TCP server in the background, call from REPL:
    # tcp.start()
