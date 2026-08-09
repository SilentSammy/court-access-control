import sys
sys.path.insert(0, 'server')
from schedule import GlobalSchedule, RoomSchedule, ScheduleDisplayer
from session import Session, Timestamp
from datetime import datetime, timedelta
import os

# Load the complex schedule we just created
schedule_file = os.path.join(os.path.dirname(__file__), 'schedule_complex.csv')
gs = GlobalSchedule(file_path=schedule_file)

# Base time
base_time = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
base_ts = int(base_time.timestamp())

print("=== Testing Schedule Preview & Highlight Features ===\n")

# Get all current sessions
all_sessions = gs.get_schedule()
print(f"Current sessions in schedule: {len(all_sessions)}\n")

# Create RoomSchedule for Squash courts
squash_sch = RoomSchedule(gs, room_ids=[1, 2, 3])
squash_sch.name_map = {
    1: "Squash A",
    2: "Squash B",
    3: "Squash C",
}
squash_sch.name = "Squash Courts"

# Create displayer
displayer = ScheduleDisplayer(squash_sch)
displayer.start_date = base_time.date()
displayer.day_span = 2

print(f"Displayer title: {displayer.title}\n")

# Find alice's sessions to highlight
alice_sessions = squash_sch.get_user_schedule('alice')
print(f"Alice's sessions ({len(alice_sessions)}):")
for item in alice_sessions:
    print(f"  - Room {item.session.room}: {datetime.fromtimestamp(item.session.start).strftime('%H:%M')}-{datetime.fromtimestamp(item.session.end).strftime('%H:%M')}")

# Set alice as the user to highlight
displayer.user_id = 'alice'

# Create a session to add (preview) - Room 2, 16:00-16:30 (small 30-min gap)
session_to_add = Session(base_ts + 7200, 30, 2)  # 16:00-16:30 in room 2
displayer.sessions_to_add = [session_to_add]
print(f"\nSession to ADD (yellow preview):")
print(f"  - Room {session_to_add.room}: {datetime.fromtimestamp(session_to_add.start).strftime('%H:%M')}-{datetime.fromtimestamp(session_to_add.end).strftime('%H:%M')} (30m)")

# Create a session to cancel - Bob's session (Room 2, 14:00-15:00)
bob_session = next((s.session for s in all_sessions if s.user == 'bob'), None)
if bob_session:
    displayer.sessions_to_cancel = [bob_session]
    print(f"\nSession to CANCEL (red highlight):")
    print(f"  - Room {bob_session.room}: {datetime.fromtimestamp(bob_session.start).strftime('%H:%M')}-{datetime.fromtimestamp(bob_session.end).strftime('%H:%M')} (bob)")
else:
    print("\n✗ Could not find bob's session to cancel")

print(f"\nColor scheme:")
print(f"  - Cyan (cyan-bg): Alice's sessions (user_id={displayer.user_id})")
print(f"  - Yellow (yellow-bg): Session to add preview")
print(f"  - Red (red-bg): Session to cancel")
print(f"  - Gray (gray-bg): Other sessions")

print(f"\n=== Generating Preview Schedule Image ===\n")

try:
    print(f"Arranging schedule...")
    scheduled = displayer.arrange_schedule()
    print(f"Arranged {len(scheduled)} schedule items for display")
    
    print(f"Generating image with previews...")
    image_path = displayer.display()
    print(f"\n✓ SUCCESS: Preview image generated at {image_path}")
    
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
