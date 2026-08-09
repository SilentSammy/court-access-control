import sys
sys.path.insert(0, 'server')
from schedule import GlobalSchedule
from datetime import datetime

gs = GlobalSchedule(file_path='schedule.csv')
schedule = gs.get_schedule()

print(f'Total sessions: {len(schedule)}\n')
for item in schedule:
    start_dt = datetime.fromtimestamp(item.session.start)
    end_dt = datetime.fromtimestamp(item.session.end)
    print(f'Room {item.session.room}: {start_dt.strftime("%Y-%m-%d %H:%M")} - {end_dt.strftime("%H:%M")} ({item.session.span} min) | User: {item.user}')
