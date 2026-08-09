import sys
sys.path.insert(0, 'server')
from schedule import GlobalSchedule, RoomSchedule
from session import Session, Timestamp
from datetime import datetime

# Load existing schedule
gs = GlobalSchedule(file_path='schedule.csv')
room_schedule = RoomSchedule(gs, [1])

print("=== Existing Sessions ===")
for item in room_schedule.schedule:
    start_dt = datetime.fromtimestamp(item.session.start)
    end_dt = datetime.fromtimestamp(item.session.end)
    print(f'Room 1: {start_dt.strftime("%H:%M")} - {end_dt.strftime("%H:%M")}')

print("\n=== Testing Conflict Detection ===\n")

# Test 1: Try to book overlapping time (21:00-22:00 overlaps with 20:22-21:22)
test_time_1 = Timestamp.from_datetime(2026, 8, 8, 21, 0, 0)
session_1 = Session(test_time_1, 60, 1)
start_dt = datetime.fromtimestamp(session_1.start)
end_dt = datetime.fromtimestamp(session_1.end)
available = room_schedule.is_available(session_1)
print(f"Test 1 - Book {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')} (overlaps 20:22-21:22)")
print(f"  Result: {'✓ AVAILABLE' if available else '✗ CONFLICT DETECTED (expected)'}\n")

# Test 2: Try to book completely free time (19:00-20:00 is between 19:52 end and 20:22 start)
test_time_2 = Timestamp.from_datetime(2026, 8, 8, 19, 0, 0)
session_2 = Session(test_time_2, 60, 1)
start_dt = datetime.fromtimestamp(session_2.start)
end_dt = datetime.fromtimestamp(session_2.end)
available = room_schedule.is_available(session_2)
print(f"Test 2 - Book {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')} (already booked 18:52-19:52)")
print(f"  Result: {'✓ AVAILABLE' if available else '✗ CONFLICT DETECTED (expected)'}\n")

# Test 3: Try to book completely free time (19:55-20:15)
test_time_3 = Timestamp.from_datetime(2026, 8, 8, 19, 55, 0)
session_3 = Session(test_time_3, 20, 1)
start_dt = datetime.fromtimestamp(session_3.start)
end_dt = datetime.fromtimestamp(session_3.end)
available = room_schedule.is_available(session_3)
print(f"Test 3 - Book {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')} (gap between 19:52 and 20:22)")
print(f"  Result: {'✓ AVAILABLE (expected)' if available else '✗ CONFLICT DETECTED'}\n")

# Test 4: Try to book at exact boundary (starts when another ends - 19:52)
test_time_4 = Timestamp.from_datetime(2026, 8, 8, 19, 52, 0)
session_4 = Session(test_time_4, 30, 1)
start_dt = datetime.fromtimestamp(session_4.start)
end_dt = datetime.fromtimestamp(session_4.end)
available = room_schedule.is_available(session_4)
print(f"Test 4 - Book {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')} (starts exactly when 18:52-19:52 ends)")
print(f"  Result: {'✓ AVAILABLE (expected)' if available else '✗ CONFLICT DETECTED'}\n")

# Test 5: Different room (should be available regardless)
test_time_5 = Timestamp.from_datetime(2026, 8, 8, 21, 0, 0)
session_5 = Session(test_time_5, 60, 0)
start_dt = datetime.fromtimestamp(session_5.start)
end_dt = datetime.fromtimestamp(session_5.end)
available = room_schedule.is_available(session_5)
print(f"Test 5 - Book Room 0 at {start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')} (different room)")
print(f"  Result: {'✓ AVAILABLE (expected)' if available else '✗ CONFLICT DETECTED'}")
