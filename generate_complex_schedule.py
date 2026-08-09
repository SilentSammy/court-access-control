import sys
sys.path.insert(0, 'server')
from schedule import GlobalSchedule, RoomSchedule, ScheduleDisplayer
from session import Session, Timestamp
from datetime import datetime, timedelta
import os

# Create fresh schedule for testing
schedule_file = os.path.join(os.path.dirname(__file__), 'schedule_complex.csv')
gs = GlobalSchedule(file_path=schedule_file)

# Base time: today at 2 PM
base_time = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0)
base_ts = int(base_time.timestamp())

print("=== Creating Complex Test Scenario ===\n")
print(f"Base time: {base_time}\n")

# Scenario 1: All three squash rooms booked at same time (14:00-15:00)
print("Scenario 1: All 3 rooms booked at same time (14:00-15:00)")
s1_r1 = Session(base_ts, 60, 1)
s1_r2 = Session(base_ts, 60, 2)
s1_r3 = Session(base_ts, 60, 3)
gs.add_session(s1_r1, 'alice')
gs.add_session(s1_r2, 'bob')
gs.add_session(s1_r3, 'charlie')
print(f"  ✓ Added 3 sessions\n")

# Scenario 2: Slightly offset times with overlaps
# Room 1: 15:30-16:30
# Room 2: 16:00-17:00 (overlaps with room 1 from 16:00-16:30)
# Room 3: 15:00-15:45 (earlier, doesn't overlap with others yet)
print("Scenario 2: Offset times with partial overlaps")
s2_r3 = Session(base_ts + 3600, 45, 3)  # 15:00-15:45
s2_r1 = Session(base_ts + 5400, 60, 1)  # 15:30-16:30
s2_r2 = Session(base_ts + 5760, 60, 2)  # 16:00-17:00 (overlaps with s2_r1)
gs.add_session(s2_r3, 'dave')
gs.add_session(s2_r1, 'eve')
gs.add_session(s2_r2, 'frank')
print(f"  ✓ Added 3 staggered sessions with partial overlaps\n")

# Scenario 3: Chain of overlaps across rooms
# Room 1: 17:00-18:00
# Room 2: 17:30-18:30 (overlaps with room 1: 17:30-18:00)
# Room 3: 18:00-19:00 (overlaps with room 2: 18:00-18:30, but NOT room 1)
print("Scenario 3: Chain of overlaps (1→2→3 but 1 doesn't overlap 3)")
s3_r1 = Session(base_ts + 10800, 60, 1)  # 17:00-18:00
s3_r2 = Session(base_ts + 12600, 60, 2)  # 17:30-18:30
s3_r3 = Session(base_ts + 14400, 60, 3)  # 18:00-19:00
gs.add_session(s3_r1, 'grace')
gs.add_session(s3_r2, 'henry')
gs.add_session(s3_r3, 'iris')
print(f"  ✓ Added 3 chained overlap sessions\n")

# Scenario 4: Very short session (30 min) squeezed between longer ones
print("Scenario 4: Short 30-minute session")
s4_r1 = Session(base_ts + 18000, 30, 1)  # 19:00-19:30 (fits between s1 and s3)
gs.add_session(s4_r1, 'jack')
print(f"  ✓ Added short 30-min session\n")

# Scenario 5: Sessions spanning late into night/midnight
print("Scenario 5: Late sessions spanning to next day")
s5_r2 = Session(base_ts + 32400, 120, 2)  # 23:00-01:00 (spans midnight)
s5_r3 = Session(base_ts + 36000, 120, 3)  # 00:00-02:00 (completely past midnight)
gs.add_session(s5_r2, 'kate')
gs.add_session(s5_r3, 'liam')
print(f"  ✓ Added sessions spanning midnight\n")

# Scenario 6: Gap in room 1 for afternoon
print("Scenario 6: Intentional gap (room 1 free from 16:30-19:00)")
print(f"  (demonstrates availability detection)\n")

# Display all sessions
print("=== All Sessions Summary ===\n")
all_sessions = gs.get_schedule()
for item in sorted(all_sessions, key=lambda x: (x.session.room, x.session.start)):
    start_dt = datetime.fromtimestamp(item.session.start)
    end_dt = datetime.fromtimestamp(item.session.end)
    print(f"Room {item.session.room}: {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')} ({item.session.span}m) | {item.user}")

# Create RoomSchedule for Squash courts
squash_sch = RoomSchedule(gs, room_ids=[1, 2, 3])
squash_sch.name_map = {
    1: "Squash A",
    2: "Squash B",
    3: "Squash C",
}
squash_sch.name = "Squash Courts"

print(f"\n=== Generating Schedule Display ===\n")

# Try to generate display
try:
    displayer = ScheduleDisplayer(squash_sch)
    print(f"Displayer title: {displayer.title}")
    
    # Adjust start date to show all data
    displayer.start_date = base_time.date()
    displayer.day_span = 2  # Show 2 days to see midnight spanning
    
    print(f"Date range: {displayer.start_date} to {displayer.end_date}")
    print(f"Arranging schedule...")
    scheduled = displayer.arrange_schedule()
    print(f"Arranged {len(scheduled)} schedule items for display")
    
    print(f"\nGenerating image...")
    image_path = displayer.display()
    print(f"\n✓ SUCCESS: Image generated at {image_path}")
    
except FileNotFoundError as e:
    print(f"✗ Missing template files: {e}")
except RuntimeError as e:
    print(f"✗ Runtime error: {e}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
