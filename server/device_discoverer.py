import asyncio
import aiohttp
import json
import socket
import ipaddress
import os
from datetime import datetime

class DeviceDiscoverer:
    """Discovers and tracks IoT devices on the network."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, discovery_interval=60, health_check_interval=5, cache_file=None, scan_networks=None):
        """Initialize discoverer with scan intervals.
        
        Args:
            discovery_interval: Seconds between full network scans
            health_check_interval: Seconds between health checks of known devices
            cache_file: Path to cache file for discovered devices
            scan_networks: List of CIDR networks to scan (e.g., ["192.168.137.0/24", "10.22.128.0/20"])
                          If None, auto-detects and scans all local networks with /24 assumption
                          If empty list, no scanning is performed
        """
        if hasattr(self, '_initialized'):
            return
        self._initialized = True
        
        self.discovery_interval = discovery_interval
        self.health_check_interval = health_check_interval
        self.cache_file = cache_file or os.path.join(
            os.path.dirname(__file__), 
            '.device_cache.json'
        )
        self.scan_networks = scan_networks
        
        self.devices = {}  # ip -> {device_type, endpoints, last_seen}
        self.endpoint_map = {}  # endpoint -> ip
        
        self._discovery_task = None
        self._health_check_task = None
        self._running = False
        
        self._load_cache()
    
    def _load_cache(self):
        """Load discovered devices from cache file."""
        try:
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
                for ip, device in data.get('devices', {}).items():
                    device['last_seen'] = datetime.fromisoformat(device['last_seen'])
                    self.devices[ip] = device
                    for endpoint in device['endpoints']:
                        self.endpoint_map[endpoint] = ip
        except:
            pass
    
    def _save_cache(self):
        """Save discovered devices to cache file."""
        try:
            data = {'devices': {}}
            for ip, device in self.devices.items():
                device_copy = device.copy()
                device_copy['last_seen'] = device['last_seen'].isoformat()
                data['devices'][ip] = device_copy
            with open(self.cache_file, 'w') as f:
                json.dump(data, f)
        except:
            pass
    
    def _get_all_local_networks(self):
        """Get all local network subnets to scan."""
        # If scan_networks is configured, use that
        if self.scan_networks is not None:
            if not self.scan_networks:  # Empty list = no scanning
                return None
            networks = []
            for cidr in self.scan_networks:
                try:
                    network = ipaddress.IPv4Network(cidr, strict=False)
                    networks.append(network)
                except:
                    pass
            return networks if networks else None
        
        # Auto-detect networks (fallback to /24 assumption)
        networks = []
        try:
            hostname = socket.gethostname()
            _, _, ip_list = socket.gethostbyname_ex(hostname)
            for ip in ip_list:
                if not ip.startswith('127.'):
                    network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
                    if network not in networks:
                        networks.append(network)
        except:
            pass
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
            if network not in networks:
                networks.append(network)
        except:
            pass
        
        return networks if networks else None
    
    async def _check_device(self, ip):
        """Check if device has device-info endpoint and return its data."""
        try:
            url = f"http://{ip}/device-info"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                    if response.status == 200:
                        text = await response.text()
                        data = json.loads(text)
                        return {
                            'ip': ip,
                            'device_type': data.get('device_type'),
                            'endpoints': data.get('endpoints', []),
                            'last_seen': datetime.now()
                        }
        except:
            pass
        return None
    
    async def discover_devices(self):
        """Scan network and update device/endpoint mappings."""
        networks = self._get_all_local_networks()
        if not networks:
            return
        
        sem = asyncio.Semaphore(20)
        
        async def check_with_semaphore(ip):
            async with sem:
                return await self._check_device(ip)
        
        tasks = []
        for network in networks:
            for ip in network.hosts():
                tasks.append(check_with_semaphore(str(ip)))
        
        for coro in asyncio.as_completed(tasks):
            device = await coro
            if device:
                ip = device['ip']
                self.devices[ip] = device
                
                # Update endpoint map
                for endpoint in device['endpoints']:
                    self.endpoint_map[endpoint] = ip
        
        self._save_cache()
    
    async def _health_check_loop(self):
        """Periodically check if discovered devices are still online."""
        while self._running:
            await asyncio.sleep(self.health_check_interval)
            if not self._running:
                break
            
            ips = list(self.devices.keys())
            cache_changed = False
            for ip in ips:
                device = await self._check_device(ip)
                if device:
                    self.devices[ip] = device
                    for endpoint in device['endpoints']:
                        self.endpoint_map[endpoint] = ip
                    cache_changed = True
                else:
                    # Device offline - remove it
                    removed_device = self.devices.pop(ip, None)
                    if removed_device:
                        for endpoint in removed_device['endpoints']:
                            self.endpoint_map.pop(endpoint, None)
                        cache_changed = True
            
            if cache_changed:
                self._save_cache()
    
    async def _discovery_loop(self):
        """Periodically scan network for new devices."""
        while self._running:
            await asyncio.sleep(self.discovery_interval)
            if not self._running:
                break
            await self.discover_devices()
    
    def start_continuous_discovery(self):
        """Start background discovery and health check tasks."""
        if not self._running:
            self._running = True
            self._discovery_task = asyncio.create_task(self._discovery_loop())
            self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    def stop_continuous_discovery(self):
        """Stop background tasks."""
        self._running = False
    
    def endpoint_exists(self, endpoint):
        """Check if endpoint is available on any device."""
        return endpoint in self.endpoint_map
    
    def complete_url(self, endpoint):
        """Return full URL for endpoint or None if not found."""
        ip = self.endpoint_map.get(endpoint)
        if ip:
            return f"http://{ip}/{endpoint}"
        return None
    
    def get_all_endpoints(self):
        """Return list of all discovered endpoints."""
        return list(self.endpoint_map.keys())
    
    def get_devices(self):
        """Return device inventory for debugging."""
        return self.devices

async def _demo():
    """Demo showing DeviceDiscoverer usage."""
    
    discoverer = DeviceDiscoverer(
        discovery_interval=30, 
        health_check_interval=5,
        scan_networks=[
            "192.168.137.0/24",  # Windows hotspot
            "192.168.1.0/24"     # Home network (check ipconfig at home)
        ]
        # Or use scan_networks=None to auto-detect all networks
    )
    
    print("=== DeviceDiscoverer Demo ===")
    print("Discovery runs every 30s, health checks every 5s")
    print(f"Scanning networks: {discoverer.scan_networks}")
    print("Devices appear as they're found (real-time)")
    print("Press Ctrl+C to stop\n")
    
    discoverer.start_continuous_discovery()
    
    try:
        while True:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Devices: {len(discoverer.devices)} | Endpoints: {len(discoverer.get_all_endpoints())}")
            for ip, device in discoverer.devices.items():
                print(f"  {ip}: {device['device_type']} ({len(device['endpoints'])} endpoints)")
            await asyncio.sleep(5)
    except KeyboardInterrupt:
        print("\n\nStopping...")
        discoverer.stop_continuous_discovery()
        await asyncio.sleep(1)
        print("Stopped.")

if __name__ == "__main__":
    asyncio.run(_demo())
