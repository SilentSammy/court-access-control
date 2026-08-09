import sys
sys.path.insert(0, 'server')
from schedule import GlobalSchedule, RoomSchedule, ScheduleDisplayer
from session import Session
from datetime import datetime
import os

# Load schedule
gs = GlobalSchedule(file_path='schedule.csv')

# Create RoomSchedule for room 1 (which has data)
room1_sch = RoomSchedule(gs, room_ids=1)
room1_sch.name_map = {1: "Tennis Court"}
room1_sch.name = "Tennis"

print(f"Sessions in Room 1: {len(room1_sch.schedule)}")
for item in room1_sch.schedule:
    print(f"  - {item}")

# Try to generate display
try:
    displayer = ScheduleDisplayer(room1_sch)
    print(f"\nDisplayer title: {displayer.title}")
    print(f"Arranging schedule...")
    scheduled = displayer.arrange_schedule()
    print(f"Arranged {len(scheduled)} schedule items")
    print("\nAttempting to generate image...")
    image_path = displayer.display()
    print(f"✓ Image generated: {image_path}")
except FileNotFoundError as e:
    print(f"✗ Missing template files: {e}")
    print("\nTemplate files needed:")
    template_dir = os.path.join(os.path.dirname(__file__), 'server', 'schedule')
    for fname in ['index.txt', 'header.txt', 'column.txt', 'cell.txt', 'timeline.txt', 'style.css']:
        print(f"  - {os.path.join(template_dir, fname)}")
except RuntimeError as e:
    print(f"✗ Runtime error: {e}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
