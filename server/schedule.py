import csv
import math
import os
import random
from datetime import datetime, date, timedelta, time
from string import Template
from session import Session, Timestamp

_DIR = os.path.dirname(os.path.abspath(__file__))

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
        return self.start - timedelta(minutes=Schedule.CANCEL_DEADLINE_MINS) < datetime.now()

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


class Schedule:
    CANCEL_DEADLINE_MINS = 30
    LAST_UPDATE: float = 0
    _SESSIONS: set = set()
    _FILE_PATH = os.path.join(_DIR, 'schedule.csv')

    # Room id → display name mapping.  Populated at startup from discovered devices.
    ROOMS: dict = {}

    def __init__(self, room=None):
        self.room_id = room

    # ── Internal helpers ───────────────────────────────────────────────────────

    @classmethod
    def _refresh_sessions(cls):
        """Read sessions from the CSV file, discarding any that have ended."""
        cls._SESSIONS.clear()
        overwrite = False

        if not os.path.exists(cls._FILE_PATH):
            return

        with open(cls._FILE_PATH, 'r', newline='') as f:
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
                    cls._SESSIONS.add(ScheduleItem.from_session(sess, user))
                except (OSError, ValueError, OverflowError):
                    overwrite = True  # drop corrupted session
                    continue

        if overwrite:
            cls.overwrite_sessions()

    @classmethod
    def get_schedule(cls):
        """Return sorted sessions, re-reading from disk when the file changes."""
        if not os.path.exists(cls._FILE_PATH):
            return []
        if os.path.getmtime(cls._FILE_PATH) > cls.LAST_UPDATE:
            cls.LAST_UPDATE = os.path.getmtime(cls._FILE_PATH)
            cls._refresh_sessions()
        return sorted(cls._SESSIONS, key=lambda s: s.start)

    # ── Instance helpers ───────────────────────────────────────────────────────

    @property
    def schedule(self):
        """All sessions, optionally filtered to this room."""
        all_sessions = Schedule.get_schedule()
        if self.room_id is None:
            return all_sessions
        return [s for s in all_sessions if s.session.room == self.room_id]

    def get_gaps(self, start=None, sessions=None):
        """Return gaps between sessions starting from a given datetime."""
        sessions = sorted(sessions, key=lambda s: s.start) if sessions else self.schedule
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

    def is_available(self, session: Session) -> bool:
        """True if the session does not conflict with any existing booking."""
        return not any(si.session.conflicts_with(session) for si in self.schedule)

    def add_session(self, session: Session, user: str) -> bool:
        """Book a session.  Returns False if the slot is taken."""
        if not self.is_available(session):
            return False

        item = ScheduleItem.from_session(session, user)
        Schedule._SESSIONS.add(item)

        # Ensure the file exists
        os.makedirs(os.path.dirname(Schedule._FILE_PATH), exist_ok=True)
        with open(Schedule._FILE_PATH, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([session.full_code, user])

        Schedule.LAST_UPDATE = os.path.getmtime(Schedule._FILE_PATH)
        return True

    @staticmethod
    def delete_session(session: Session) -> bool:
        """Remove a session from storage."""
        item = next(
            (s for s in Schedule.get_schedule() if s.session.full_code == session.full_code),
            None
        )
        if item is None:
            return False
        try:
            Schedule._SESSIONS.discard(item)
            Schedule.overwrite_sessions()
            return True
        except Exception:
            return False

    @staticmethod
    def overwrite_sessions():
        """Rewrite the CSV from the in-memory set."""
        sessions = Schedule.get_schedule()
        with open(Schedule._FILE_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            for item in sessions:
                writer.writerow([item.session.full_code, item.user])
        Schedule.LAST_UPDATE = os.path.getmtime(Schedule._FILE_PATH)

    @staticmethod
    def get_user_schedule(user: str):
        """Return ScheduleItems belonging to the given user."""
        return [s for s in Schedule.get_schedule() if s.user == user]

    @staticmethod
    def find_available_room(room_ids: list, start: int, span: int):
        """Try each room in room_ids and return the first available Session, or None.

        Builds a correctly-roomed Session per candidate and delegates to
        the existing is_available() -> conflicts_with() chain.
        """
        for rid in room_ids:
            candidate = Session(start, span, int(rid))
            if Schedule(int(rid)).is_available(candidate):
                return candidate
        return None

    @staticmethod
    def max_instant_duration(room_ids: list, start: int, max_minutes: int = 120) -> int:
        """Return the longest bookable duration (minutes) available right now across
        any room in room_ids, capped at max_minutes.  Returns 0 if no room is free."""
        start_dt = datetime.fromtimestamp(start)
        best = 0
        for rid in room_ids:
            sch = Schedule(int(rid))
            sessions = sch.schedule
            # Skip if any session is active right now
            if any(si.start <= start_dt < si.end for si in sessions):
                continue
            # Find the earliest session starting after `start`
            future = [si for si in sessions if si.start > start_dt]
            if not future:
                return max_minutes  # fully free — no need to look further
            earliest = min(future, key=lambda si: si.start)
            free_mins = int((earliest.start - start_dt).total_seconds() / 60)
            best = max(best, min(free_mins, max_minutes))
        return best


# ── Visual display (requires html2image) ──────────────────────────────────────

class ScheduleDisplayer:
    BASE_DIR = os.path.join(_DIR, 'schedule')
    COLORS = [
        'red-bg', 'green-bg', 'blue-bg', 'yellow-bg',
        'purple-bg', 'orange-bg', 'pink-bg', 'gray-bg',
    ]

    def __init__(self, schedules):
        # Accept a single Schedule or a list of Schedules (for group/multi-room display)
        if isinstance(schedules, Schedule):
            schedules = [schedules]
        self.schedules = schedules
        self.schedule = schedules[0]  # used for title fallback and backward compat
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
        return f"Schedule for {Schedule.ROOMS.get(self.schedule.room_id, f'Room {self.schedule.room_id}')}"

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
        room_ids = [s.room_id for s in self.schedules]
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

def add_random_sessions(n=1, schedule: Schedule = None, days=5, day_offset=None):
    start = datetime.now()
    if day_offset is not None:
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        start += timedelta(days=day_offset)
    else:
        start = start.replace(minute=0, second=0, microsecond=0)
        start += timedelta(hours=1)

    intervals = [random.randint(0, 24 * days) for _ in range(n)]
    datetimes = [start + timedelta(hours=i) for i in intervals]
    sessions = [Session(int(dt.timestamp()), 120, schedule.room_id) for dt in datetimes]

    for session in sessions:
        added = schedule.add_session(session, 'test_user')
        print(f"{'Added' if added else 'Not added (conflict)'} session {session.full_code}")


if __name__ == '__main__':
    import tempfile, shutil

    # ── Redirect storage to a temp file ───────────────────────────────────────
    _orig_path = Schedule._FILE_PATH
    _tmp_dir = tempfile.mkdtemp()
    Schedule._FILE_PATH = os.path.join(_tmp_dir, 'schedule.csv')
    Schedule._SESSIONS.clear()
    Schedule.LAST_UPDATE = 0

    print("=== schedule.py tests ===")

    now_ts = int(datetime.now().timestamp())
    future = now_ts + 7200   # 2 hours from now
    past   = now_ts - 7200   # 2 hours ago

    # ── Test 1: empty schedule ─────────────────────────────────────────────────
    sch0 = Schedule(room=0)
    assert sch0.schedule == [], "Expected empty schedule"
    print("[PASS] Empty schedule returns []")

    # ── Test 2: add a future session ──────────────────────────────────────────
    s1 = Session(future, 60, 0)
    added = Schedule(0).add_session(s1, 'alice')
    assert added, "Expected session to be added"
    assert len(Schedule(0).schedule) == 1
    print("[PASS] Add future session")

    # ── Test 3: conflict detection ────────────────────────────────────────────
    s2 = Session(future + 1800, 60, 0)   # overlaps with s1
    added2 = Schedule(0).add_session(s2, 'bob')
    assert not added2, "Expected conflict to be detected"
    print("[PASS] Conflict detection works")

    # ── Test 4: non-conflicting same room ─────────────────────────────────────
    s3 = Session(future + 3600 + 7200, 60, 0)   # starts well after s1 ends
    added3 = Schedule(0).add_session(s3, 'bob')
    assert added3, "Expected non-conflicting session to be added"
    print("[PASS] Non-conflicting session added")

    # ── Test 5: different rooms don't conflict ────────────────────────────────
    s4 = Session(future, 60, 1)   # same time, different room
    added4 = Schedule(1).add_session(s4, 'alice')
    assert added4, "Expected session in different room to be added"
    print("[PASS] Different rooms don't conflict")

    # ── Test 6: get_user_schedule ─────────────────────────────────────────────
    alice_sessions = Schedule.get_user_schedule('alice')
    assert len(alice_sessions) == 2   # s1 (room 0) + s4 (room 1)
    print(f"[PASS] get_user_schedule: alice has {len(alice_sessions)} sessions")

    # ── Test 7: delete_session ────────────────────────────────────────────────
    deleted = Schedule.delete_session(s3)
    assert deleted, "Expected session to be deleted"
    assert len(Schedule(0).schedule) == 1
    print("[PASS] delete_session removes the session")

    # ── Test 8: ended sessions not loaded ────────────────────────────────────
    # Manually write a past session to the csv
    s_past = Session(past, 60, 0)
    with open(Schedule._FILE_PATH, 'a', newline='') as f:
        csv.writer(f).writerow([s_past.full_code, 'ghost'])
    Schedule._SESSIONS.clear()
    Schedule.LAST_UPDATE = 0   # force re-read
    loaded = Schedule.get_schedule()
    users = [si.user for si in loaded]
    assert 'ghost' not in users, "Past session should have been discarded"
    print("[PASS] Ended sessions are discarded on load")

    # ── Test 9: ScheduleItem helpers ──────────────────────────────────────────
    item = ScheduleItem.from_session(s1, 'alice')
    assert item.past_deadline() == False, "Future session should not be past deadline"
    print("[PASS] ScheduleItem.past_deadline() correct for future session")

    # ── Test 10: ScheduleDisplayer instantiates without html2image ───────────
    sd = ScheduleDisplayer(Schedule(0))
    sd.user_id = 'alice'
    html = sd.create_html(sd.arrange_schedule())
    assert '<html' in html.lower() or len(html) > 0
    print("[PASS] ScheduleDisplayer.create_html() produces output")

    if _HTML2IMAGE_AVAILABLE:
        out = sd.display()
        print(f"[PASS] ScheduleDisplayer.display() → {out}")
    else:
        print("[INFO] html2image not installed — display() skipped")

    # Cleanup
    shutil.rmtree(_tmp_dir)
    Schedule._FILE_PATH = _orig_path
    Schedule._SESSIONS.clear()
    Schedule.LAST_UPDATE = 0

    print("\n=== All tests passed ===")
