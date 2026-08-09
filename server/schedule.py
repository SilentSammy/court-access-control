import sys
import csv
import math
import os
import random
from datetime import datetime, date, timedelta, time
from string import Template
from server.session import Session, Timestamp

_DIR = os.path.dirname(os.path.abspath(__file__))

# Booking cancellation deadline (minutes before session start)
CANCEL_DEADLINE_MINS = 30

# Optional dependency: html2image is only needed for ScheduleDisplayer.display()
try:
    from html2image import Html2Image as _Html2Image
    _HTML2IMAGE_AVAILABLE = True
except ImportError:
    _HTML2IMAGE_AVAILABLE = False


def read_file(file):
    with open(file) as f:
        return f.read()


class ScheduleItem:
    """Wrapper class for a session in the schedule, with additional properties."""

    def __init__(self, start, end, session: Session = None, user: str = None):
        self.start = datetime.fromtimestamp(start) if isinstance(start, (int, float)) else start
        self.end = datetime.fromtimestamp(end) if isinstance(end, (int, float)) else end
        self.session = session
        self.user = user

    @staticmethod
    def from_session(session: Session, user=None):
        return ScheduleItem(session.start, session.end, session, user)

    @property
    def span(self):
        return self.end - self.start

    @property
    def is_start(self):
        if not self.session:
            return False
        return (datetime.fromtimestamp(self.session.start) == self.start and
                datetime.fromtimestamp(self.session.end) != self.end)

    @property
    def is_end(self):
        if not self.session:
            return False
        return (datetime.fromtimestamp(self.session.end) == self.end and
                datetime.fromtimestamp(self.session.start) != self.start)

    @property
    def start_date(self):
        return self.start.date()

    @property
    def end_date(self):
        # if end time is exactly midnight, return the day before
        return (self.end - timedelta(microseconds=1)).date()

    def falls_within(self, start, end):
        """Check if the item falls within the given range (end is exclusive)."""
        start = start if isinstance(start, datetime) else datetime.combine(start, time())
        end = end if isinstance(end, datetime) else datetime.combine(end, time())
        return self.start < end and self.end >= start

    def falls_on(self, d):
        """Check if the item falls on the given date."""
        return self.falls_within(
            datetime.combine(d, time()),
            datetime.combine(d + timedelta(days=1), time())
        )

    def past_deadline(self):
        """True if the cancellation deadline has passed."""
        return self.start - timedelta(minutes=CANCEL_DEADLINE_MINS) < datetime.now()

    def clone(self, start=None, end=None):
        return ScheduleItem(start or self.start, end or self.end, self.session, self.user)

    def __str__(self):
        return (f'{"Session" if self.session else "Gap    "}: '
                f'{self.start} - {self.end}'
                f'{(" " + self.user) if self.session else ""}')

    def __repr__(self):
        return self.__str__()

    # Hash/eq based on underlying session so ScheduleItems can live in sets
    def __hash__(self):
        return hash(self.session) if self.session else hash((self.start, self.end))

    def __eq__(self, other):
        if not isinstance(other, ScheduleItem):
            return False
        return self.session == other.session and self.user == other.user


class GlobalSchedule:
    """Class to manage the global schedule across all rooms."""

    def __init__(self, file_path="schedule.csv"):
        self.last_update = 0
        self._sessions = set()
        self.file_path = file_path

    def get_schedule(self):
        """Return sorted sessions, re-reading from disk when the file changes."""
        if not os.path.exists(self.file_path):
            # Create the directory if it doesn't exist (only if there's a directory in the path)
            dir_path = os.path.dirname(self.file_path)
            if dir_path:  # Only create directory if path contains a directory
                os.makedirs(dir_path, exist_ok=True)
            return []
        if os.path.getmtime(self.file_path) > self.last_update:
            self.last_update = os.path.getmtime(self.file_path)
            self._refresh_sessions()
        return sorted(self._sessions, key=lambda s: s.start)

    def _refresh_sessions(self):
        """Read sessions from the CSV file, discarding any that have ended."""
        self._sessions.clear()
        overwrite = False

        if not os.path.exists(self.file_path):
            return

        with open(self.file_path, 'r', newline='') as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                full_code = int(row[0])
                user = row[1] if len(row) > 1 else ''
                sess = Session.from_code(full_code)
                if sess.has_ended():
                    overwrite = True
                    continue
                try:
                    self._sessions.add(ScheduleItem.from_session(sess, user))
                except (OSError, ValueError, OverflowError):
                    overwrite = True  # drop corrupted session
                    continue

        if overwrite:
            self._overwrite_sessions()

    def _overwrite_sessions(self):
        """Rewrite the CSV from the in-memory set."""
        with open(self.file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            for item in self._sessions:
                writer.writerow([item.session.full_code, item.user])
        self.last_update = os.path.getmtime(self.file_path)

    def add_session(self, session: Session, user: str):
        """Adds a session to the global schedule. Returns the ScheduleItem."""

        item = ScheduleItem.from_session(session, user)
        self._sessions.add(item)

        # Ensure the directory exists (only if there's a directory in the path)
        dir_path = os.path.dirname(self.file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(self.file_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([session.full_code, user])

        self.last_update = os.path.getmtime(self.file_path)

        return item

    def delete_session(self, session: Session) -> bool:
        """Remove a session from storage. Returns True if deleted."""
        item = next(
            (s for s in self.get_schedule() if s.session.full_code == session.full_code),
            None
        )
        if item is None:
            return False
        try:
            self._sessions.discard(item)
            self._overwrite_sessions()
            return True
        except Exception:
            return False

    def get_user_schedule(self, user: str):
        """Return ScheduleItems belonging to the given user."""
        return [s for s in self.get_schedule() if s.user == user]


class RoomSchedule:
    """Schedule view for a specific room or group of rooms."""
    
    def __init__(self, global_schedule: GlobalSchedule, room_ids, name_map=None, name=None):
        """
        Args:
            global_schedule: The GlobalSchedule instance to query
            room_ids: Single room ID or list of room IDs this schedule manages
        """
        self.global_schedule = global_schedule
        # Normalize to list for consistent handling
        self.room_ids = room_ids if isinstance(room_ids, list) else [room_ids]
        self.name_map = name_map if name_map is not None else {}  # room_id -> display name mapping
        self.name = name    # name for the entire room group
    
    @property
    def schedule(self):
        """Return ScheduleItems filtered to this room group."""
        all_sessions = self.global_schedule.get_schedule()
        return [s for s in all_sessions if s.session.room in self.room_ids]
    
    def is_available(self, session: Session) -> bool:
        """Check if a specific session is available.
        
        Validates:
        1. Session's room is in our group
        2. No conflicts with existing bookings in that room
        """
        if session.room not in self.room_ids:
            return False  # Room not in our group
        
        # Only check conflicts in the same room
        return not any(
            si.session.conflicts_with(session) 
            for si in self.schedule 
            if si.session.room == session.room
        )
    
    def add_session(self, session: Session, user: str) -> bool:
        """Book a session if available. Returns False if unavailable."""
        if not self.is_available(session):
            return False
        
        self.global_schedule.add_session(session, user)
        return True
    
    def delete_session(self, session: Session) -> bool:
        """Remove a session from storage. Returns True if deleted."""
        return self.global_schedule.delete_session(session)
    
    def get_user_schedule(self, user: str):
        """Return ScheduleItems belonging to the given user, filtered to this room group."""
        return [s for s in self.schedule if s.user == user]
    
    def find_available_room(self, start: int, span: int):
        """Try each room in group, return first available Session or None."""
        for room_id in self.room_ids:
            candidate = Session(start, span, room_id)
            if self.is_available(candidate):
                return candidate
        return None
    
    def max_instant_duration(self, start: int, max_minutes: int = 120) -> int:
        """Return longest bookable duration available now across all rooms.
        Returns 0 if no room is free."""
        start_dt = datetime.fromtimestamp(start)
        best = 0
        
        for room_id in self.room_ids:
            # Get sessions for just this room
            room_sessions = [s for s in self.schedule if s.session.room == room_id]
            
            # Skip if room currently occupied
            if any(si.start <= start_dt < si.end for si in room_sessions):
                continue
            
            # Find next booking in this room
            future = [si for si in room_sessions if si.start > start_dt]
            if not future:
                return max_minutes  # Fully free, no need to check others
            
            earliest = min(future, key=lambda si: si.start)
            free_mins = int((earliest.start - start_dt).total_seconds() / 60)
            best = max(best, min(free_mins, max_minutes))
        
        return best
    
    def get_gaps(self, start=None):
        """Return gaps between sessions in this room group."""
        sessions = sorted(self.schedule, key=lambda s: s.start)
        if start:
            sessions = [s for s in sessions if s.end >= start]
        if not sessions:
            return []
        
        gaps = []
        if start and start < sessions[0].start:
            gaps.append(ScheduleItem(start, sessions[0].start))
        
        for i in range(len(sessions) - 1):
            gaps.append(ScheduleItem(sessions[i].end, sessions[i + 1].start))
        
        return gaps


# ── Visual display (requires html2image) ──────────────────────────────────────

class ScheduleDisplayer:
    BASE_DIR = os.path.join(_DIR, 'schedule')
    COLORS = [
        'red-bg', 'green-bg', 'blue-bg', 'yellow-bg',
        'purple-bg', 'orange-bg', 'pink-bg', 'gray-bg',
    ]

    def __init__(self, schedules):
        # Accept a single RoomSchedule or a list of RoomSchedules (for group/multi-room display)
        if isinstance(schedules, RoomSchedule):
            schedules = [schedules]
        self.schedules = schedules
        self.schedule = schedules[0]  # used for title and property access
        self.main_tmpl = Template(read_file(os.path.join(self.BASE_DIR, 'index.txt')))
        self.header_tmpl = Template(read_file(os.path.join(self.BASE_DIR, 'header.txt')))
        self.column_tmpl = Template(read_file(os.path.join(self.BASE_DIR, 'column.txt')))
        self.cell_tmpl = Template(read_file(os.path.join(self.BASE_DIR, 'cell.txt')))
        self.timeline_tmpl = Template(read_file(os.path.join(self.BASE_DIR, 'timeline.txt')))
        self._title = None
        self.css_str = read_file(os.path.join(self.BASE_DIR, 'style.css'))

        self.output_filename = 'output.png'
        self.hti = _Html2Image(output_path=self.BASE_DIR) if _HTML2IMAGE_AVAILABLE else None

        self.sessions_to_add: list = None
        self.sessions_to_cancel: list = None
        self.user_id: str = None

        self.start_date = datetime.today().date()
        self.day_span = 7
        self.session_color = 'gray-bg'
        self.user_color = 'cyan-bg'
        self.preview_color = 'yellow-bg'
        self.cancel_color = 'red-bg'

    def get_color(self, item: ScheduleItem):
        if self.sessions_to_add and item.session in self.sessions_to_add:
            return self.preview_color
        if self.sessions_to_cancel and item.session in self.sessions_to_cancel:
            return self.cancel_color
        if item.user == self.user_id:
            return self.user_color
        if item.session:
            return self.session_color
        return 'gray-bg'

    @property
    def title(self):
        if self._title is not None:
            return self._title
        
        # Use the group name if available
        if self.schedule.name:
            return f"Schedule for {self.schedule.name}"
        
        # Single room: use name_map or fallback to room ID
        if len(self.schedule.room_ids) == 1:
            room_id = self.schedule.room_ids[0]
            room_name = self.schedule.name_map.get(room_id, f"Room {room_id}")
            return f"Schedule for {room_name}"
        
        # Multiple rooms: list them
        return f"Schedule for Rooms {', '.join(map(str, self.schedule.room_ids))}"

    @title.setter
    def title(self, value):
        self._title = value

    @property
    def days(self):
        return [self.start_date + timedelta(days=i) for i in range(self.day_span)]

    @property
    def end_date(self):
        return self.days[-1]

    @property
    def cutoff_date(self):
        return self.end_date + timedelta(days=1)

    def arrange_schedule(self):
        sessions = []
        for sch in self.schedules:
            sessions += sch.schedule
        sessions = [s for s in sessions if s.falls_within(self.start_date, self.cutoff_date)]

        if self.sessions_to_add:
            sessions += [ScheduleItem.from_session(s, 'preview') for s in self.sessions_to_add]

        sessions.sort(key=lambda s: s.start)
        new_schedule = []

        for item in sessions:
            datetimes = [max(item.start, datetime.combine(self.start_date, time()))]
            datetimes += [
                datetime.combine(item.start_date + timedelta(days=i + 1), time())
                for i in range((item.end_date - item.start_date).days)
            ]
            datetimes += [item.end]

            for i in range(len(datetimes) - 1):
                new_schedule.append(item.clone(datetimes[i], datetimes[i + 1]))

        return new_schedule

    @staticmethod
    def _assign_subcolumns(sessions, k):
        """Group sessions into overlap-chains and return a map of
        ScheduleItem -> (col_start, col_span) in subcolumn units.

        Two sessions overlap when their intervals share any interior point
        (start < other.end and end > other.start).  Overlap is transitive:
        if a↔b and b↔c, then a, b, c all land in the same group.

        Within a group of m sessions each cell spans k//m subcolumns,
        assigned at positions 0, k//m, 2*(k//m), … sorted by start time.
        """
        n = len(sessions)
        if n == 0:
            return {}

        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            parent[find(x)] = find(y)

        for i in range(n):
            for j in range(i + 1, n):
                if sessions[i].start < sessions[j].end and sessions[i].end > sessions[j].start:
                    union(i, j)

        components = {}
        for i in range(n):
            components.setdefault(find(i), []).append(i)

        result = {}
        for comp_indices in components.values():
            m = len(comp_indices)
            col_span = k // m
            for pos, idx in enumerate(sorted(comp_indices, key=lambda i: (sessions[i].start, i))):
                result[sessions[idx]] = (pos * col_span, col_span)
        return result

    def create_html(self, schedule):
        schedule = [item for item in schedule if item.session]
        days = sorted(self.days)
        # Flatten room_ids from all RoomSchedules
        room_ids = []
        for s in self.schedules:
            room_ids.extend(s.room_ids)
        n = len(room_ids)
        k = math.lcm(*range(1, n + 1))  # total subcolumns per day column

        headers = ""
        for day in days:
            headers += self.header_tmpl.substitute({
                'day': day.strftime('%A %d %B'),
                'class': ScheduleDisplayer.COLORS[day.weekday() % len(ScheduleDisplayer.COLORS)],
            }) + "\n"

        columns = ""
        for i, day in enumerate(days):
            day_sessions = [s for s in schedule if s.start.date() == day]
            subcol_map = ScheduleDisplayer._assign_subcolumns(day_sessions, k)
            cells = ""
            for item in day_sessions:
                col_start, col_span = subcol_map.get(item, (0, k))
                if n == 1:
                    style = ""
                else:
                    style = f"left: {col_start / k * 100:.4f}%; width: {col_span / k * 100:.4f}%;"

                color = self.get_color(item)
                cell_class = (color
                              + (" start" if item.is_start else "")
                              + (" end" if item.is_end else "")
                              + (" tiny" if item.span <= timedelta(minutes=30) else ""))
                start = (item.start - item.start.replace(
                    hour=0, minute=0, second=0, microsecond=0)).total_seconds()
                start /= (24 * 60 * 60)
                span = item.span.seconds / (24 * 60 * 60)
                if item.session:
                    time_str = datetime.fromtimestamp(item.session.start).strftime('%H:%M')
                    span_str = "{:02d}".format(int(item.session.span)) + "m"
                    room_str = str(item.session.room)
                    if n == 1:
                        content = f"{time_str} for {span_str}"
                    elif col_span == k:
                        content = f"Room {room_str} @ {time_str} for {span_str}"
                    else:
                        content = room_str
                else:
                    content = ""

                cells += self.cell_tmpl.substitute({
                    'class': cell_class,
                    'start': str(start),
                    'span': span,
                    'content': content,
                    'style': style,
                }) + "\n"

            if day == datetime.today().date():
                now_frac = (datetime.now() - datetime.now().replace(
                    hour=0, minute=0, second=0, microsecond=0)).total_seconds() / (24 * 60 * 60)
                cells += self.timeline_tmpl.substitute({'start': now_frac}) + "\n"

            columns += self.column_tmpl.substitute(cells=cells) + "\n"

        html = self.main_tmpl.substitute(headers=headers, columns=columns, title=self.title)

        html_path = os.path.join(self.BASE_DIR, 'index.html')
        with open(html_path, 'w') as f:
            f.write(html)

        return html

    def display(self):
        if not _HTML2IMAGE_AVAILABLE:
            raise RuntimeError(
                "html2image is not installed. Run: pip install html2image"
            )
        schedule = self.arrange_schedule()
        html = self.create_html(schedule)
        images = self.hti.screenshot(
            html_str=html,
            css_str=self.css_str,
            save_as=self.output_filename,
        )
        return images[0]


# ── Utilities ─────────────────────────────────────────────────────────────────


if __name__ == '__main__':
    import tempfile, shutil

    print("=== Testing GlobalSchedule and RoomSchedule ===\n")

    # Create a temporary directory for testing
    _tmp_dir = tempfile.mkdtemp()
    test_file = os.path.join(_tmp_dir, 'test_schedule.csv')

    # Initialize GlobalSchedule
    global_schedule = GlobalSchedule(file_path=test_file)

    now_ts = int(datetime.now().timestamp())
    future = now_ts + 7200   # 2 hours from now
    future2 = now_ts + 14400  # 4 hours from now

    # Test 1: Add sessions to global schedule
    s1 = Session(future, 60, 0)
    item1 = global_schedule.add_session(s1, 'alice')
    assert item1 is not None, "Expected session to be added"
    print("[PASS] GlobalSchedule.add_session works")

    # Test 2: Create RoomSchedule for room 0
    room0_schedule = RoomSchedule(global_schedule, room_ids=0)
    assert len(room0_schedule.schedule) == 1, "Expected 1 session in room 0"
    print("[PASS] RoomSchedule filters sessions correctly")

    # Test 3: Add to different room via RoomSchedule
    s2 = Session(future, 60, 1)
    added = room0_schedule.add_session(s2, 'bob')
    assert not added, "Expected add to fail (room 1 not in room0_schedule)"
    print("[PASS] RoomSchedule rejects sessions for other rooms")

    # Test 4: RoomSchedule for multiple rooms
    squash_courts = RoomSchedule(global_schedule, room_ids=[0, 1, 2])
    s3 = Session(future2, 60, 1)
    added = squash_courts.add_session(s3, 'charlie')
    assert added, "Expected session to be added to room 1"
    assert len(squash_courts.schedule) == 2, "Expected 2 sessions in squash group"
    print("[PASS] RoomSchedule works with multiple rooms")

    # Test 5: Conflict detection
    s4 = Session(future + 1800, 60, 0)  # Overlaps with s1
    added = room0_schedule.add_session(s4, 'dave')
    assert not added, "Expected conflict detection"
    print("[PASS] Conflict detection works")

    # Test 6: find_available_room
    available_session = squash_courts.find_available_room(future + 7200, 60)
    assert available_session is not None, "Expected to find available room"
    assert available_session.room in [0, 1, 2], "Expected room in squash group"
    print(f"[PASS] find_available_room found room {available_session.room}")

    # Test 7: get_user_schedule
    alice_sessions = squash_courts.get_user_schedule('alice')
    assert len(alice_sessions) == 1, "Expected 1 session for alice in squash courts"
    print("[PASS] RoomSchedule.get_user_schedule works")

    # Test 8: delete_session via RoomSchedule
    deleted = room0_schedule.delete_session(s1)
    assert deleted, "Expected session to be deleted"
    assert len(room0_schedule.schedule) == 0, "Expected no sessions in room 0"
    print("[PASS] RoomSchedule.delete_session works")

    # Test 9: max_instant_duration
    # Add a session at future, room 0
    s6 = Session(future, 60, 0)
    global_schedule.add_session(s6, 'eve')
    duration = squash_courts.max_instant_duration(now_ts, max_minutes=120)
    assert duration > 0, "Expected some available duration"
    print(f"[PASS] max_instant_duration returned {duration} minutes")

    # Cleanup
    shutil.rmtree(_tmp_dir)
    print("\n=== All tests passed ===")

