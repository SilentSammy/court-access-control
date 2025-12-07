import csv
import random
import os
from datetime import datetime, date, timedelta, time
from session import *
from html2image import Html2Image
from string import Template

os.chdir(os.path.dirname(os.path.realpath(__file__)))

def read_file(file):
    with open(file) as f:
        return f.read()


class ScheduleItem:
    """Wrapper class for a session in the schedule, with additional properties and methods"""
    def __init__(self, start:datetime, end:datetime, session:Session=None, user:str=None):
        self.start = datetime.fromtimestamp(start) if isinstance(start, (int, float)) else start
        self.end = datetime.fromtimestamp(end) if isinstance(end, (int, float)) else end
        self.session = session
        self.user = user
    
    @staticmethod
    def from_session(session, user=None):
        return ScheduleItem(session.start, session.end, session, user)

    @property
    def span(self):
        return self.end - self.start

    @property
    def is_start(self):
        return (datetime.fromtimestamp(self.session.start) == self.start and datetime.fromtimestamp(self.session.end) != self.end) if self.session else False
    
    @property
    def is_end(self):
        return (datetime.fromtimestamp(self.session.end) == self.end and datetime.fromtimestamp(self.session.start) != self.start) if self.session else False

    @property
    def start_date(self):
        return self.start.date()
    
    @property
    def end_date(self):
        # if the end time is 00:00, we return the date before it
        return (self.end - timedelta(microseconds=1)).date()
    
    def falls_within(self, start, end):
        """Check if the ScheduleItem falls within the given range of datetimes or dates (the end datetime is excluded from the range)"""
        start = start if isinstance(start, datetime) else datetime.combine(start, time())
        end = end if isinstance(end, datetime) else datetime.combine(end, time())
        return self.start < end and self.end >= start

    def falls_on(self, date):
        """Check if the ScheduleItem falls on the given date"""
        return self.falls_within(datetime.combine(date, time()), datetime.combine(date + timedelta(days=1), time()))

    def past_deadline(self):
        """Check if the ScheduleItem is past the deadline for cancellation"""
        return self.start - timedelta(minutes=Schedule.CANCEL_DEADLINE_MINS) < datetime.now()

    def clone(self, start=None, end=None):
        """Return a new ScheduleItem with the same session and user, but with different start and end datetimes"""
        return ScheduleItem(start or self.start, end or self.end, self.session, self.user)

    def __str__(self) -> str:
        return f'{"Session" if self.session else "Gap    "}: {self.start} - {self.end}{(" " + self.user) if self.session else ""}'

    def __repr__(self) -> str:
        return self.__str__()

class Schedule:
    CANCEL_DEADLINE_MINS = 30
    LAST_UPDATE = 0
    _SESSIONS = set()
    _FILE_PATH = 'schedule.csv'
    ROOMS = {
        0: 'Squash',
        1: 'Racquetball',
        2: 'Padel',
    }

    def __init__(self, room=None):
        self.room_id = room

    @classmethod
    def _refresh_sessions(cls):
        """Read the sessions from the csv file and store them in the sessions set"""

        # we clear the sessions set
        cls._SESSIONS.clear()

        # we create a flag to know whether we need to overwrite the file
        overwrite = False

        # we read every line in the csv file using the csv module
        with open(cls._FILE_PATH, 'r') as f:
            reader = csv.reader(f)
            for row in reader:
                # check if row is empty
                if not row: continue

                # we get the session and the user from the row
                full_code = int(row[0])
                user = row[1]

                # we create a session object from the session code
                sess = Session.from_code(full_code)

                # if the session has ended, we skip it, and we set a flag to make sure we overwrite the file at the end of the loop
                if sess.has_ended():
                    overwrite = True
                    continue

                item = ScheduleItem.from_session(sess, user)
                cls._SESSIONS.add(item)
        
        # if we need to overwrite the file, we do so. This is to remove any sessions that have ended
        if overwrite:
            cls.overwrite_sessions()

    @classmethod
    def get_schedule(cls):
        """Return the sorted sessions, updating them if the csv file has been updated"""
        # check if the file has been updated
        if os.path.getmtime(cls._FILE_PATH) > cls.LAST_UPDATE:
            cls.LAST_UPDATE = os.path.getmtime(cls._FILE_PATH) # KEEP THIS LINE HERE, DON'T MOVE IT DOWN
            cls._refresh_sessions()
        
        # return the sorted sessions
        sessions = sorted(cls._SESSIONS, key=lambda s: s.start)
        return sessions

    @property
    def schedule(self):
        """Returns the class-level sessions set, filtered for the room"""
        all_sessions = Schedule.get_schedule()
        if self.room_id is None:
            return all_sessions
        room_sessions = [s for s in all_sessions if s.session.room == self.room_id]
        return room_sessions

    def get_gaps(self, start=None, sessions=None):
        """Return a list of gaps between sessions, starting from a given datetime"""

        # we get the sessions. if they are provided externally, we must sort them
        sessions = sorted(sessions, key=lambda s: s.start) if sessions else self.schedule

        # we get the sessions that end after or at the start datetime
        sessions = [s for s in sessions if s.end >= start] if start else sessions
        
        # if there are no sessions, we return an empty list
        if not sessions: return []
        
        # we create an empty list to hold the gaps
        gaps = []

        # if the start datetime is before the start of the first session
        if (start < sessions[0].start) if start else False:
            # we append a gap between the start datetime and the start of the first session
            gaps.append(ScheduleItem(start, sessions[0].start))

        # we loop through all the sessions except the last one, because we are comparing it to the next one
        for i in range(len(sessions)-1):
            # we append a gap between the end of the current session and the start of the next session
            gaps.append(ScheduleItem(sessions[i].end, sessions[i+1].start))
        
        return list(gaps)

    def is_available(self, session):
        # we check if the session conficts with any of the sessions in the schedule
        for sess in self.schedule:
            if sess.session.conflicts_with(session):
                return False
        return True
    
    def add_session(self, session:Session, user:str):
        # we check if the session is available
        if not self.is_available(session):
            return False
        
        # we append the session to the sessions set
        item = ScheduleItem.from_session(session, user)
        Schedule._SESSIONS.add(item)

        # we write the session to the csv file
        with open(Schedule._FILE_PATH, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([session.full_code, user])
        
        # update the last update time, so that the sessions aren't read from the file again
        Schedule.LAST_UPDATE = os.path.getmtime(Schedule._FILE_PATH)

        return True

    @staticmethod
    def delete_session(session:Session):
        """Delete a session from the csv file"""
        # we find the first ScheduleItem that has the session
        item = next((s for s in Schedule.get_schedule() if s.session.full_code == session.full_code), None)

        try:
            Schedule._SESSIONS.remove(item) # we remove the session from the sessions set
            Schedule.overwrite_sessions() # we overwrite the sessions in the csv file
            return True
        except KeyError:
            return False


    @staticmethod
    def overwrite_sessions():
        """Overwrite the sessions in the csv file with the sessions in the class-level sessions set"""
        # we get the sessions before overwriting them
        sessions = Schedule.get_schedule()

        # we write the sessions to the csv file
        with open(Schedule._FILE_PATH, 'w', newline='') as f:
            writer = csv.writer(f)
            for item in sessions:
                writer.writerow([item.session.full_code, item.user])
        
        # update the last update time, so that the sessions aren't read from the file again
        Schedule.LAST_UPDATE = os.path.getmtime(Schedule._FILE_PATH)

    @staticmethod
    def get_user_schedule(user:str):
        """Return a list of ScheduleItems for the sessions that the user has booked"""
        return [s for s in Schedule.get_schedule() if s.user == user]

class ScheduleDisplayer:
    BASE_DIR = 'schedule'
    COLORS = [
        'red-bg',
        'green-bg',
        'blue-bg',
        'yellow-bg',
        'purple-bg',
        'orange-bg',
        'pink-bg',
        'gray-bg'
    ]

    def __init__(self, schedule:Schedule):
        self.schedule = schedule

        # we read the html templates
        self.main_tmpl = Template(read_file(ScheduleDisplayer.BASE_DIR + '/index.txt'))
        self.header_tmpl = Template(read_file(ScheduleDisplayer.BASE_DIR + '/header.txt'))
        self.column_tmpl = Template(read_file(ScheduleDisplayer.BASE_DIR + '/column.txt'))
        self.cell_tmpl = Template(read_file(ScheduleDisplayer.BASE_DIR + '/cell.txt'))
        self.timeline_tmpl = Template(read_file(ScheduleDisplayer.BASE_DIR + '/timeline.txt'))
        self._title = None

        # we read the css file
        self.css_str = read_file(ScheduleDisplayer.BASE_DIR + '/style.css')
        
        # we define config parameters
        self.output_filename = 'output.png'

        # we create the html2image object
        self.hti = Html2Image(output_path=ScheduleDisplayer.BASE_DIR)

        # we define the preview sessions and the user
        self.sessions_to_add:list = None
        self.sessions_to_cancel:list = None
        self.user_id:str = None

        # we define default config parameters
        self.start_date = datetime.today().date()
        self.day_span = 7
        self.session_color = 'gray-bg'
        self.user_color = 'cyan-bg'
        self.preview_color = 'yellow-bg'
        self.cancel_color = 'red-bg'

    def get_color(self, item:ScheduleItem):
        if self.sessions_to_add and item.session in self.sessions_to_add:
            return self.preview_color
        if self.sessions_to_cancel and item.session in self.sessions_to_cancel:
            return self.cancel_color
        if item.user == self.user_id:
            return self.user_color
        if item.session:
            return self.session_color
        return 'gray-bg'

    @property
    def title(self):
        return self._title if self._title is not None else f"Schedule for {Schedule.ROOMS.get(self.schedule.room_id, f'Room {self.schedule.room_id}')}"

    @title.setter
    def title(self, title):
        self._title = title

    @property
    def days(self):
        """Return a list of dates in the range
        Example: if self.day_span == 1, we only get [start_day].
        Example: If self.day_span == 2, we get [start_day, start_day + 1]."""
        return [self.start_date + timedelta(days=i) for i in range(self.day_span)]

    @property
    def end_date(self):
        """Returns the last date (inclusive) to be displayed in the schedule"""
        return self.days[-1]

    @property
    def cutoff_date(self):
        """Returns the last date (exclusive) to be displayed in the schedule"""
        return self.end_date + timedelta(days=1)

    def arrange_schedule(self):
        """Returns a list of ScheduleItems where the items do not span across days.
        Example: if a session starts on one day and ends on another, we get two items, one for each day.
        """

        # get and filter the sessions
        sessions = self.schedule.schedule
        sessions = [s for s in sessions if s.falls_within(self.start_date, self.cutoff_date)] # filter the sessions to the days we want to display

        # optionally append the preview session
        if self.sessions_to_add:
            sessions += [ScheduleItem.from_session(s, 'preview') for s in self.sessions_to_add]

        # get the gaps in the schedule
        schd = sessions #+ self.schedule.get_gaps(datetime.combine(self.start_date, time()), sessions)

        # sort the schedule by start time
        schd.sort(key=lambda s: s.start)

        # create a list to hold the arranged schedule
        new_schedule = []

        # loop through the items in the schedule
        for item in schd:
            # we define the start of the item as the start of the schedule or the start of the item, whichever is later
            datetimes = [max(item.start, datetime.combine(self.start_date, time()))]

            # we get the datetimes at midnight for the days the item spans across
            datetimes += [datetime.combine(item.start_date + timedelta(days=i+1), time()) for i in range((item.end_date - item.start_date).days)]

            # we define the end of the item as the end of the schedule or the end of the item, whichever is earlier
            # datetimes += [min(item.end, datetime.combine(self.end_date, time()))]
            datetimes += [item.end]

            # we loop through the datetimes, except the last one, because we are comparing it to the next one
            for i in range(len(datetimes)-1):
                # Create a new schedule item
                new_schedule.append(item.clone(datetimes[i], datetimes[i+1]))
        
        return new_schedule

    def create_html(self, schedule):
        # remove the gaps from the schedule
        schedule = [item for item in schedule if item.session]

        # get the days in the schedule
        days = self.days
        days.sort()
        
        # create the headers
        headers = ""
        for day in days:
            headers += self.header_tmpl.substitute(
                {
                    'day': day.strftime('%A %d %B'),
                    'class': ScheduleDisplayer.COLORS[day.weekday() % len(ScheduleDisplayer.COLORS)],
                }
            ) + "\n"
        
        # create the columns
        columns = ""
        for i in range(len(days)):
            cells = ""
            
            # for every ScheduleItem
            for item in [item for item in schedule if item.start.date() == days[i]]:
                # type hint
                item:ScheduleItem = item
                
                # we get all of the cell's properties
                color = self.get_color(item)
                cell_class = color + (" start" if item.is_start else "") + (" end" if item.is_end else "") + (" tiny" if item.span <= timedelta(minutes=30) else "")
                start = (item.start - item.start.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
                start /= (24*60*60)
                span = item.span.seconds / (24*60*60)
                content = (datetime.fromtimestamp(item.session.start)).strftime('%H:%M') + " for " + "{:02d}".format(int(item.session.span)) + "m" if item.session else ""

                # we insert the cell's properties into the cell HTML template
                cell_html = self.cell_tmpl.substitute(
                    {
                        'class': cell_class,
                        'start': str(start),
                        'span': span,
                        'content': content,
                    }
                ) + "\n"

                # we append the cell to the cells string
                cells += cell_html
            
            # if this column is today
            if days[i] == datetime.today().date():
                # we append the timeline to the cells string
                cells += self.timeline_tmpl.substitute({
                    'start': (datetime.now() - datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() / (24*60*60),
                }) + "\n"

            columns += self.column_tmpl.substitute(cells=cells) + "\n"
        
        # create the html
        html = self.main_tmpl.substitute(headers=headers, columns=columns, title=self.title)

        # save the html to a file
        with open('schedule/index.html', 'w') as f:
            f.write(html)

        return html

    def display(self):
        schedule = self.arrange_schedule()
        html = self.create_html(schedule)

        # convert the html file to an image
        images = self.hti.screenshot(
            html_str=html,
            css_str=self.css_str,
            save_as=self.output_filename,
        )
        return images[0]

def add_random_sessions(n=1, schedule:Schedule=None, days=5, day_offset=None):
    start = datetime.now()

    if day_offset is not None:
        # we round up to the start of the day
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        start += timedelta(days=day_offset) # we add (or subtract) the day_offset
        # if day_offset is less than or equal to 0, we might get a time in the past (which is ok for testing purposes)
    else:
        # we round up to the next hour
        # this ensures all sessions start at the beginning of the hour, and in the future
        start = start.replace(minute=0, second=0, microsecond=0)
        start += timedelta(hours=1)

    # we create a list of 10 random ints between 0 and 24*days
    intervals = [random.randint(0, 24*days) for i in range(n)]

    # we create a list of datetimes, starting from the start datetime, with intervals between each datetime
    datetimes = [start + timedelta(hours=i) for i in intervals]

    # we create a list of sessions from the datetimes
    sessions = [Session(start=dt.timestamp(), span=120, room=schedule.room_id) for dt in datetimes]

    # we add the sessions to the schedule
    for session in sessions:
        # we attempt to add the session to the schedule
        added = schedule.add_session(session, 'user')

        # we print whether the session was added or not
        print(f"{'Added' if added else 'Not added'} session {session.full_code}")

def show_all_schedules(user:str = '50766180742', rooms = [0, 1, 2]):
    for room in rooms:
        schedule = Schedule(room=room)
        sd = ScheduleDisplayer(schedule)
        sd.user_id = user
        output = sd.display()
        os.startfile(output)

def generate_schedules(rooms= [0, 1, 2]):
    for room in rooms:
        sch = Schedule(room=room)
        for sch_item in sch.schedule:
            sch.delete_session(sch_item.session)
        add_random_sessions(20, sch, days=9, day_offset=-2)

if __name__ == "__main__":
    generate_schedules()
    # show_all_schedules()
