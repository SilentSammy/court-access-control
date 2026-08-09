"""Generate random sessions for testing the schedule."""
import random
from datetime import datetime, timedelta
from server.session import Session, Timestamp
from schedule_config import global_schedule

# Configuration
NUM_SESSIONS = 20  # Number of sessions to generate
MIN_DURATION = 30  # Minimum session duration in minutes
MAX_DURATION = 120  # Maximum session duration in minutes
DAYS_AHEAD = 5  # Generate sessions within the next N days
ROOM_IDS = [1, 2, 3]  # Squash court room IDs

# Hardcoded user list
USER_IDS = ['5218111547752', '50766180742', '5218114142626']

def generate_random_session(base_time: datetime):
    """Generate a random session starting from base_time."""
    # Random offset from base_time (0 to DAYS_AHEAD days)
    offset_hours = random.randint(0, DAYS_AHEAD * 24)
    # Round to nearest 30 minutes
    offset_minutes = random.choice([0, 30])
    
    start_time = base_time + timedelta(hours=offset_hours, minutes=offset_minutes)
    # Set seconds to 0 for cleaner timestamps
    start_time = start_time.replace(second=0, microsecond=0)
    
    # Random duration (30, 60, 90, or 120 minutes)
    duration = random.choice([30, 60, 90, 120])
    
    # Random room
    room_id = random.choice(ROOM_IDS)
    
    # Create session (convert datetime to Unix timestamp)
    start_timestamp = Timestamp(int(start_time.timestamp()))
    session = Session(start_timestamp, duration, room_id)
    
    return session, start_time, duration, room_id

def main():
    print("=== Generating Random Sessions ===\n")
    
    # Use hardcoded user IDs
    print(f"Using {len(USER_IDS)} users: {', '.join(USER_IDS)}\n")
    
    # Use current time as base
    now = datetime.now()
    print(f"Base time: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"Generating {NUM_SESSIONS} sessions over the next {DAYS_AHEAD} days...\n")
    
    # Generate and add sessions
    added_count = 0
    failed_count = 0
    
    for i in range(NUM_SESSIONS):
        # Pick random user
        user_id = random.choice(USER_IDS)
        
        # Generate random session
        session, start_time, duration, room_id = generate_random_session(now)
        
        # Try to add it (will fail if conflicts)
        try:
            # Check if available first
            from schedule_config import squash_schedule
            if squash_schedule.is_available(session):
                schedule_item = global_schedule.add_session(session, user_id)
                added_count += 1
                print(f"✓ Added: Room {room_id}, {start_time.strftime('%Y-%m-%d %H:%M')}, "
                      f"{duration}min, User: {user_id}")
            else:
                failed_count += 1
                print(f"✗ Conflict: Room {room_id}, {start_time.strftime('%Y-%m-%d %H:%M')}, "
                      f"{duration}min (skipped)")
        except Exception as e:
            failed_count += 1
            print(f"✗ Error adding session: {e}")
    
    print(f"\n=== Summary ===")
    print(f"Successfully added: {added_count} sessions")
    print(f"Failed/Conflicts: {failed_count} sessions")
    print(f"Total attempts: {NUM_SESSIONS}")
    
    # Show current schedule count
    all_sessions = global_schedule.get_schedule()
    print(f"\nTotal sessions in schedule: {len(all_sessions)}")

if __name__ == '__main__':
    main()
