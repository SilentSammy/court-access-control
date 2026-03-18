from session import Session
import threading
import time

class SessionManager:
    def __init__(self, check_interval=5):
        """Initialize with check interval in seconds."""
        self.sessions = []
        self.active_sessions = set()
        self.check_interval = check_interval
        self._running = False
        self._thread = None
        
        # Configurable callbacks
        self.start_session = None
        self.end_session = None
    
    def add_session(self, session):
        """Add a session to the manager."""
        self.sessions.append(session)
    
    def remove_session(self, session):
        """Remove a session from the manager."""
        if session in self.sessions:
            self.sessions.remove(session)
        if session in self.active_sessions:
            self.active_sessions.remove(session)
    
    def set_sessions(self, sessions):
        """Replace all sessions with a new list."""
        self.sessions = list(sessions)
        self.active_sessions.clear()
    
    def _check_sessions(self):
        """Check all sessions and trigger callbacks as needed."""
        for session in self.sessions[:]:
            # Check if session should start
            if session.has_started() and session not in self.active_sessions and not session.has_ended():
                self.active_sessions.add(session)
                if self.start_session:
                    self.start_session(session)
            
            # Check if session should end
            if session.has_ended() and session in self.active_sessions:
                self.active_sessions.remove(session)
                if self.end_session:
                    self.end_session(session)
    
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
