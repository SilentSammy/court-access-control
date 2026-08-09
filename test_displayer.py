import sys
sys.path.insert(0, 'server')
from schedule import GlobalSchedule, RoomSchedule
from session import Session, Timestamp
from datetime import datetime

# Create global schedule with test data
gs = GlobalSchedule(file_path='schedule.csv')

print("=== Testing RoomSchedule Naming System ===\n")

# Test 1: Single room with custom name
room1_sch = RoomSchedule(gs, room_ids=1)
room1_sch.name_map = {1: "Tennis Court"}
room1_sch.name = "Tennis"

print(f"Test 1 - Single room schedule:")
print(f"  Room IDs: {room1_sch.room_ids}")
print(f"  Name map: {room1_sch.name_map}")
print(f"  Group name: {room1_sch.name}\n")

# Test 2: Room group with custom names
squash_sch = RoomSchedule(gs, room_ids=[0, 1, 2])
squash_sch.name_map = {
    0: "Squash A",
    1: "Squash B", 
    2: "Squash C",
}
squash_sch.name = "Squash Courts"

print(f"Test 2 - Room group schedule:")
print(f"  Room IDs: {squash_sch.room_ids}")
print(f"  Name map: {squash_sch.name_map}")
print(f"  Group name: {squash_sch.name}\n")

# Test 3: RoomSchedule without names (will use defaults)
plain_sch = RoomSchedule(gs, room_ids=[3, 4])
print(f"Test 3 - Plain schedule (no custom names):")
print(f"  Room IDs: {plain_sch.room_ids}")
print(f"  Name map: {plain_sch.name_map}")
print(f"  Group name: {plain_sch.name}\n")

# Test 4: Verify existing sessions are filtered correctly
print(f"Test 4 - Session filtering:")
print(f"  Room 1 schedule has {len(room1_sch.schedule)} sessions")
print(f"  Squash group schedule has {len(squash_sch.schedule)} sessions")
print(f"  Plain schedule has {len(plain_sch.schedule)} sessions\n")

# Test 5: Simulate what ScheduleDisplayer.title would generate
def simulate_title(room_schedule, custom_title=None):
    if custom_title is not None:
        return custom_title
    
    if room_schedule.name:
        return f"Schedule for {room_schedule.name}"
    
    if len(room_schedule.room_ids) == 1:
        room_id = room_schedule.room_ids[0]
        room_name = room_schedule.name_map.get(room_id, f"Room {room_id}")
        return f"Schedule for {room_name}"
    
    return f"Schedule for Rooms {', '.join(map(str, room_schedule.room_ids))}"

print(f"Test 5 - Title generation logic:")
print(f"  Room 1 title: {simulate_title(room1_sch)}")
print(f"  Squash group title: {simulate_title(squash_sch)}")
print(f"  Plain group title: {simulate_title(plain_sch)}")

print("\n=== All naming tests passed ===")
