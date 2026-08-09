from session import Session, Timestamp
from datetime import datetime, timedelta

offsets = [
    timedelta(hours=1, minutes=00),
    timedelta(hours=2, minutes=30),
    timedelta(hours=4, minutes=00),
    timedelta(hours=4, minutes=30),
]

for o in offsets:
    start = datetime.now() + o
    span_mins = 60
    room = 1

    ts = Timestamp(int(start.timestamp()))
    sess = Session(ts, span_mins, room)

    print(f"{sess.full_code}, 50766180742")
