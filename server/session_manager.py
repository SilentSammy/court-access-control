from server.session import Session
import threading
import time
import os

class SessionManager:
    """
    Manages the hardware control queue (sessions.txt) for automated room access control.
    
    Runs a background thread that monitors sessions.txt and triggers callbacks when
    sessions start/end. This is separate from schedule.csv (booking database) and
    serves as a hardware control interface that any system can write to.
    
    Key features:
    - File-based persistence (survives restarts)
    - Auto-cleanup of ended sessions
    - Thread-safe operation
    - Configurable callbacks for hardware control
    """
    
    def __init__(self, check_interval=5, sessions_file="sessions.txt"):
        """Initialize with check interval in seconds and sessions file path."""
        self.sessions_file = sessions_file
        self.active_sessions = set()
        self.check_interval = check_interval
        self._running = False
        self._thread = None
        
        # Configurable callbacks
        self.start_session = None  # Called when session starts: start_session(session)
        self.end_session = None    # Called when session ends: end_session(session)
        
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
                            session = Session.from_code(int(line))
                            sessions.append(session)
                        except (ValueError, TypeError):
                            # Skip malformed lines
                            pass
        except FileNotFoundError:
            self._ensure_file_exists()
        return sessions
    
    def add_session(self, session):
        """Add a session to the hardware control queue by appending to the file."""
        with open(self.sessions_file, 'a') as f:
            f.write(f"{int(session)}\n")
    
    def remove_session(self, session):
        """Remove a session from the queue by rewriting the file."""
        sessions = self._read_sessions()
        sessions = [s for s in sessions if s != session]
        
        # Rewrite file
        with open(self.sessions_file, 'w') as f:
            for s in sessions:
                f.write(f"{int(s)}\n")
        
        # Also remove from active sessions if present
        if session in self.active_sessions:
            self.active_sessions.remove(session)
    
    def set_sessions(self, sessions):
        """Replace all sessions by rewriting the file."""
        with open(self.sessions_file, 'w') as f:
            for session in sessions:
                f.write(f"{int(session)}\n")
        self.active_sessions.clear()
    
    def get_all_sessions(self):
        """Get all sessions from the file."""
        return self._read_sessions()
    
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
                    f.write(f"{int(s)}\n")
    
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


if __name__ == "__main__":
    """Demo showing SessionManager with test sessions."""
    from datetime import datetime
    from server.session import Session
    
    print("=== SessionManager Demo ===")
    
    # Create sessions that start in 3/5 seconds
    now_ts = int(datetime.now().timestamp())
    sessions = [
        Session(now_ts + 3, span=5, room=1),  # Starts in 3 sec, lasts 5 sec
        Session(now_ts + 5, span=3, room=2),  # Starts in 5 sec, lasts 3 sec
    ]
    
    # Set up callbacks
    def on_start(session):
        print(f"✓ Session STARTED: Room {session.room} at {datetime.now().strftime('%H:%M:%S')}")
    
    def on_end(session):
        print(f"✗ Session ENDED: Room {session.room} at {datetime.now().strftime('%H:%M:%S')}")
    
    # Create and configure manager with persistent sessions
    demo_file = "demo_sessions.txt"
    manager = SessionManager(check_interval=1, sessions_file=demo_file)
    manager.set_sessions(sessions)
    manager.start_session = on_start
    manager.end_session = on_end
    
    print("Sessions created and saved to file:")
    for s in sessions:
        start_dt = datetime.fromtimestamp(s.start)
        end_dt = datetime.fromtimestamp(s.end)
        print(f"  Room {s.room}: {start_dt.strftime('%H:%M:%S')} - {end_dt.strftime('%H:%M:%S')}")
    
    print(f"\nFile '{demo_file}' contents:")
    with open(demo_file, 'r') as f:
        for line in f:
            print(f"  {line.strip()}")
    
    print("\nStarting manager... (will run for 15 seconds)\n")
    
    manager.start()
    
    try:
        time.sleep(15)  # Run for 15 seconds
    except KeyboardInterrupt:
        pass
    finally:
        manager.stop()
        
        # Clean up demo file
        if os.path.exists(demo_file):
            os.remove(demo_file)
            print(f"\nCleaned up: {demo_file}")
        
        print("\nDemo finished.")
