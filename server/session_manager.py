from session import Session
import threading
import time
import asyncio
import os

class SessionManager:
    def __init__(self, check_interval=5, sessions_file="sessions.txt"):
        """Initialize with check interval in seconds and sessions file path."""
        self.sessions_file = sessions_file
        self.active_sessions = set()
        self.check_interval = check_interval
        self._running = False
        self._thread = None
        
        # Configurable callbacks
        self.start_session = None
        self.end_session = None
        
        # Ensure sessions file exists
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Create sessions file if it doesn't exist."""
        if not os.path.exists(self.sessions_file):
            with open(self.sessions_file, 'w') as f:
                pass  # Create empty file
    
    def _read_sessions(self):
        """Read all sessions from the file."""
        sessions = []
        try:
            with open(self.sessions_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line:  # Skip empty lines
                        try:
                            code = int(line)
                            sessions.append(Session.from_code(code))
                        except ValueError:
                            # Skip malformed lines
                            pass
        except FileNotFoundError:
            self._ensure_file_exists()
        return sessions
    
    def add_session(self, session):
        """Add a session to the manager by appending to the file."""
        with open(self.sessions_file, 'a') as f:
            f.write(f"{session.full_code}\n")
    
    def remove_session(self, session):
        """Remove a session from the manager by rewriting the file."""
        sessions = self._read_sessions()
        sessions = [s for s in sessions if s != session]
        
        # Rewrite file
        with open(self.sessions_file, 'w') as f:
            for s in sessions:
                f.write(f"{s.full_code}\n")
        
        # Also remove from active sessions if present
        if session in self.active_sessions:
            self.active_sessions.remove(session)
    
    def set_sessions(self, sessions):
        """Replace all sessions by rewriting the file."""
        with open(self.sessions_file, 'w') as f:
            for session in sessions:
                f.write(f"{session.full_code}\n")
        self.active_sessions.clear()
    
    def _check_sessions(self):
        """Check all sessions (read from file) and trigger callbacks as needed."""
        sessions = self._read_sessions()
        ended_sessions = []  # Track sessions to remove from file
        
        for session in sessions:
            # Check if session has ended - if so, end it and mark for removal
            if session.has_ended():
                if self.end_session:
                    self.end_session(session)
                ended_sessions.append(session)
                # Also remove from active tracking
                self.active_sessions.discard(session)
                continue  # Skip to next session
            
            # Check if session should start
            if session.has_started() and session not in self.active_sessions:
                self.active_sessions.add(session)
                if self.start_session:
                    self.start_session(session)
        
        # Auto-cleanup: batch remove ended sessions from file
        if ended_sessions:
            remaining = [s for s in sessions if s not in ended_sessions]
            with open(self.sessions_file, 'w') as f:
                for s in remaining:
                    f.write(f"{s.full_code}\n")
    
    def _background_loop(self):
        """Background thread loop."""
        while self._running:
            self._check_sessions()
            time.sleep(self.check_interval)
    
    def start(self):
        """Start the background monitoring thread."""
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._background_loop, daemon=True)
            self._thread.start()
    
    def stop(self):
        """Stop the background monitoring thread."""
        self._running = False
        if self._thread:
            self._thread.join()
            self._thread = None

async def _demo():
    """Demo showing SessionManager with test mode for fast testing."""
    from session import Session, Timestamp
    from facility import FacilityManager
    from device_discoverer import DeviceDiscoverer
    
    # Enable test mode: 1 "minute" = 1 second
    Timestamp.enable_test_mode()
    print("=== SessionManager Demo (TEST MODE) ===")
    print("Test mode enabled: 1 minute = 1 second\n")
    
    # Configure facility manager with home network scanning
    discoverer = DeviceDiscoverer(
        discovery_interval=30,
        health_check_interval=5,
        scan_networks=[
            "192.168.137.0/24",  # Windows hotspot
            "192.168.1.0/24"     # Home network
        ]
    )
    facility = FacilityManager(discoverer=discoverer)
    
    print("Starting device discovery...")
    facility.start_discovery()
    print("Waiting 5 seconds for devices to be discovered...\n")
    await asyncio.sleep(5)
    
    # Show discovered devices
    devices = facility.discoverer.get_devices()
    if devices:
        print(f"Found {len(devices)} device(s):")
        for ip, device in devices.items():
            print(f"  {ip}: {device['device_type']} - {device['endpoints']}")
    else:
        print("No devices found. Demo will continue in mock mode.")
    print()
    
    # Create sessions that start in 3/5 "minutes" (seconds in test mode)
    now = Timestamp.now()
    sessions = [
        Session(now + 3*Timestamp.MIN, span=5, room=1),  # Starts in 3 sec, lasts 5 sec
        Session(now + 5*Timestamp.MIN, span=3, room=2),  # Starts in 5 sec, lasts 3 sec
    ]
    
    # Get the current event loop for running coroutines from thread callbacks
    loop = asyncio.get_running_loop()
    
    # Set up callbacks with facility control
    def on_start(session):
        print(f"✓ Session STARTED: Room {session.room} at {Timestamp.now().format('%H:%M:%S')}")
        # Turn lights ON (schedule coroutine from thread)
        future = asyncio.run_coroutine_threadsafe(
            facility.control_lights(session.room, True), 
            loop
        )
        result = future.result(timeout=5)
        print(f"  → Lights ON: {result}")
    
    def on_end(session):
        print(f"✗ Session ENDED: Room {session.room} at {Timestamp.now().format('%H:%M:%S')}")
        # Turn lights OFF (schedule coroutine from thread)
        future = asyncio.run_coroutine_threadsafe(
            facility.control_lights(session.room, False), 
            loop
        )
        result = future.result(timeout=5)
        print(f"  → Lights OFF: {result}")
    
    # Create and configure manager with persistent sessions
    demo_file = "demo_sessions.txt"
    manager = SessionManager(check_interval=1, sessions_file=demo_file)
    manager.set_sessions(sessions)
    manager.start_session = on_start
    manager.end_session = on_end
    
    print("Sessions created and saved to file:")
    for s in sessions:
        print(f"  Room {s.room}: {s}")
    print(f"\nFile '{demo_file}' contents:")
    with open(demo_file, 'r') as f:
        for line in f:
            print(f"  {line.strip()}")
    print("\nStarting manager... (Press Ctrl+C to stop)\n")
    
    manager.start()
    
    try:
        await asyncio.sleep(15)  # Run for 15 seconds (enough to see both sessions start and end)
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop()
        facility.stop_discovery()
        
        # Clean up demo file
        if os.path.exists(demo_file):
            os.remove(demo_file)
            print(f"\nCleaned up: {demo_file}")
        
        print("\nDemo finished. Test mode was active: 1 minute = 1 second")

if __name__ == "__main__":
    asyncio.run(_demo())
