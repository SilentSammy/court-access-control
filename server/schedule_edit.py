from server.session import Session, Timestamp
from server.schedule import GlobalSchedule, RoomSchedule, ScheduleItem
from server.user import User

COST_PER_MINUTE = 1  # credits charged per minute of session time


class ScheduleEdit:
    """
    Represents a pending schedule modification: sessions to add and/or cancel.

    Typical usage:
        edit = ScheduleEdit(user, global_schedule, sessions_to_add=[s1], sessions_to_cancel=[s2])
        edit.apply_all_filters()   # removes invalid/unaffordable sessions in-place
        booked    = edit.book_sessions()
        cancelled = edit.cancel_sessions()
    """

    def __init__(self, user: User, global_schedule: GlobalSchedule, sessions_to_add=None, sessions_to_cancel=None):
        self.user = user
        self.global_schedule = global_schedule
        self.sessions_to_add: list = list(sessions_to_add or [])
        self.sessions_to_cancel: list = list(sessions_to_cancel or [])

    # ── Cost helpers ──────────────────────────────────────────────────────────

    @property
    def all_sessions(self):
        return self.sessions_to_add + self.sessions_to_cancel

    @staticmethod
    def get_session_cost(session: Session) -> int:
        return session.span * COST_PER_MINUTE

    @property
    def cost_to_add(self) -> int:
        return sum(self.get_session_cost(s) for s in self.sessions_to_add)

    @property
    def cancellation_refund(self) -> int:
        return sum(self.get_session_cost(s) for s in self.sessions_to_cancel)

    @property
    def net_cost(self) -> int:
        return self.cost_to_add - self.cancellation_refund

    # ── Filters (each returns the list of sessions that were removed) ─────────

    def filter_past_deadline(self) -> list:
        """Remove cancellations that are past their cancellation deadline."""
        before = list(self.sessions_to_cancel)
        self.sessions_to_cancel = [
            s for s in self.sessions_to_cancel
            if not ScheduleItem.from_session(s, self.user.id).past_deadline()
        ]
        return [s for s in before if s not in self.sessions_to_cancel]

    def filter_ended(self) -> list:
        """Remove sessions-to-add that have already ended."""
        before = list(self.sessions_to_add)
        self.sessions_to_add = [s for s in self.sessions_to_add if not s.has_ended()]
        return [s for s in before if s not in self.sessions_to_add]

    def filter_conflicting(self) -> list:
        """
        Remove sessions-to-add that conflict with each other or with the
        existing schedule (excluding sessions being cancelled in the same edit).
        
        Note: Allows overlapping sessions for the same user across different rooms
        (e.g., a coach booking multiple courts simultaneously).
        """
        before = list(self.sessions_to_add)

        # Remove sessions that conflict in the SAME room (keep first occurrence)
        temp = list(self.sessions_to_add)
        self.sessions_to_add = []
        while temp:
            candidate = temp.pop(0)
            self.sessions_to_add.append(candidate)
            # Only remove if same room AND time conflict
            temp = [s for s in temp if not (s.room == candidate.room and s.conflicts_with(candidate))]

        # Check against the existing schedule for each room
        for room in set(s.room for s in self.sessions_to_add):
            room_schedule = RoomSchedule(self.global_schedule, room_ids=room)
            existing = [si.session for si in room_schedule.schedule
                        if si.session not in self.sessions_to_cancel]
            self.sessions_to_add = [
                s for s in self.sessions_to_add
                if s.room != room or not any(s.conflicts_with(e) for e in existing)
            ]

        return [s for s in before if s not in self.sessions_to_add]

    def filter_unaffordable(self) -> list:
        """Remove sessions-to-add the user cannot afford (accounting for refunds first)."""
        before = list(self.sessions_to_add)
        available = self.user.credits + self.cancellation_refund
        affordable = []
        for s in self.sessions_to_add:
            cost = self.get_session_cost(s)
            if available >= cost:
                available -= cost
                affordable.append(s)
        self.sessions_to_add = affordable
        return [s for s in before if s not in self.sessions_to_add]

    def apply_all_filters(self):
        """Apply every filter in the correct order."""
        self.filter_past_deadline()
        self.filter_ended()
        self.filter_conflicting()
        self.filter_unaffordable()

    # ── Commit ────────────────────────────────────────────────────────────────

    def book_sessions(self) -> list:
        """
        Persist sessions_to_add and deduct their cost from the user's credits.
        Returns the list of successfully booked sessions.
        """
        booked = []
        for s in self.sessions_to_add:
            cost = self.get_session_cost(s)
            if self.user.credits < cost:
                continue
            room_schedule = RoomSchedule(self.global_schedule, room_ids=s.room)
            if room_schedule.add_session(s, self.user.id):
                self.user.credits -= cost
                booked.append(s)
        return booked

    def cancel_sessions(self) -> list:
        """
        Delete sessions_to_cancel and refund their cost to the user.
        Returns the list of successfully cancelled sessions.
        """
        cancelled = []
        for s in self.sessions_to_cancel:
            if self.global_schedule.delete_session(s):
                self.user.credits += self.get_session_cost(s)
                cancelled.append(s)
        return cancelled

    def group_by_room(self) -> dict:
        """Return {room_id: {"add": [...], "cancel": [...]}} for display purposes."""
        result = {}
        for s in self.all_sessions:
            result.setdefault(s.room, {"add": [], "cancel": []})
            if s in self.sessions_to_add:
                result[s.room]["add"].append(s)
            else:
                result[s.room]["cancel"].append(s)
        return result


if __name__ == '__main__':
    import os, tempfile, shutil
    from datetime import datetime

    # ── Setup test environment with temp files ────────────────────────────────
    _tmp_dir = tempfile.mkdtemp()
    from user import UserManager as _UM
    
    test_schedule_path = os.path.join(_tmp_dir, 'schedule.csv')
    global_schedule = GlobalSchedule(file_path=test_schedule_path)
    
    _orig_usr = _UM.FILE_PATH
    _UM.FILE_PATH = os.path.join(_tmp_dir, 'user.csv')
    _UM._USERS.clear()
    _UM._LAST_UPDATE = 0

    print("=== schedule_edit.py tests ===")

    now_ts = int(datetime.now().timestamp())
    t1 = now_ts + 3600   # 1 h from now
    t2 = now_ts + 7200   # 2 h from now
    t3 = now_ts + 10800  # 3 h from now
    t4 = now_ts + 14400  # 4 h from now

    alice = User('alice')
    alice.credits = 300

    # ── Test 1: basic book ────────────────────────────────────────────────────
    s1 = Session(t1, 60, 0)
    edit = ScheduleEdit(alice, global_schedule, sessions_to_add=[s1])
    edit.apply_all_filters()
    booked = edit.book_sessions()
    assert booked == [s1], f"Expected [s1], got {booked}"
    assert alice.credits == 300 - 60
    print(f"[PASS] Book 60-min session, credits: 300 → {alice.credits}")

    # ── Test 2: conflict rejected ─────────────────────────────────────────────
    s2 = Session(t1 + 1800, 60, 0)   # overlaps s1
    edit2 = ScheduleEdit(alice, global_schedule, sessions_to_add=[s2])
    filtered = edit2.filter_conflicting()
    assert s2 in filtered, "Conflicting session should be filtered"
    assert edit2.sessions_to_add == []
    print("[PASS] Conflicting session filtered")

    # ── Test 3: unaffordable session rejected ─────────────────────────────────
    alice.credits = 10  # only 10 credits left
    s3 = Session(t3, 60, 0)  # costs 60
    edit3 = ScheduleEdit(alice, global_schedule, sessions_to_add=[s3])
    edit3.filter_ended()
    edit3.filter_conflicting()
    filtered_unafford = edit3.filter_unaffordable()
    assert s3 in filtered_unafford, "Unaffordable session should be filtered"
    print("[PASS] Unaffordable session filtered")
    alice.credits = 300  # restore

    # ── Test 4: cancel + refund ───────────────────────────────────────────────
    credits_before = alice.credits
    edit4 = ScheduleEdit(alice, global_schedule, sessions_to_cancel=[s1])
    cancelled = edit4.cancel_sessions()
    assert s1 in cancelled
    assert alice.credits == credits_before + 60
    print(f"[PASS] Cancel session, credits: {credits_before} → {alice.credits}")

    # ── Test 5: cancel + rebook in one edit (affordability uses refund) ───────
    # alice already spent her last 60 credits on s5 — she's broke
    alice.credits = 0
    s5 = Session(t2, 60, 0)
    s6 = Session(t4, 60, 0)
    # put s5 in the schedule (credits were already deducted out-of-band)
    room0_schedule = RoomSchedule(global_schedule, room_ids=0)
    room0_schedule.add_session(s5, alice.id)

    edit5 = ScheduleEdit(alice, global_schedule, sessions_to_add=[s6], sessions_to_cancel=[s5])
    edit5.apply_all_filters()
    # net cost = 60 - 60 = 0 so should be affordable
    assert s6 in edit5.sessions_to_add, "s6 should survive filter"
    assert s5 in edit5.sessions_to_cancel, "s5 should survive filter"
    print("[PASS] Cancel + rebook in single edit (affordability accounts for refund)")

    # ── Test 6: group_by_room ─────────────────────────────────────────────────
    s7 = Session(t3, 30, 1)
    edit6 = ScheduleEdit(alice, global_schedule, sessions_to_add=[s7], sessions_to_cancel=[s5])
    groups = edit6.group_by_room()
    assert 0 in groups and 1 in groups
    assert s7 in groups[1]['add']
    assert s5 in groups[0]['cancel']
    print("[PASS] group_by_room partitions correctly")

    # Cleanup
    shutil.rmtree(_tmp_dir)
    _UM.FILE_PATH = _orig_usr
    _UM._USERS.clear()
    _UM._LAST_UPDATE = 0

    print("\n=== All tests passed ===")
