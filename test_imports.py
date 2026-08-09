#!/usr/bin/env python3
"""Quick test to verify all imports work correctly."""

print("Testing imports...")

try:
    from server.schedule_edit import ScheduleEdit
    print("✓ ScheduleEdit imported")
except Exception as e:
    print(f"✗ ScheduleEdit failed: {e}")

try:
    from server.smart_scheduler import SmartScheduler
    print("✓ SmartScheduler imported")
except Exception as e:
    print(f"✗ SmartScheduler failed: {e}")

try:
    from schedule_config import schedules
    print(f"✓ schedules imported ({len(schedules)} schedule(s))")
except Exception as e:
    print(f"✗ schedules failed: {e}")

print("\nAll imports successful!")
