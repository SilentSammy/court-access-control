import openai
import json
from datetime import datetime, timedelta, time, date
import os
from session import Session
from user import User
from schedule import Schedule, ScheduleDisplayer, read_file, ScheduleItem
import re
import json

def extract_json_objects(text):
    # Basic regex pattern for a JSON object
    # This pattern is quite naive and might not work for all valid JSON objects
    pattern = r'\{[^\{]*?\}'
    
    # Find all matches in the text
    matches = re.findall(pattern, text, re.DOTALL)
    
    # Try to parse each match as JSON
    json_objects = []
    for match in matches:
        try:
            json_obj = json.loads(match)
            json_objects.append(json_obj)
        except json.JSONDecodeError:
            # Skip if it's not a valid JSON object
            continue
    
    return json_objects

class SmartScheduler:
    """This class will process natural language and return a JSON object containing session schedule information."""
    def __init__(self, user=None):
        rooms = None
        openai.api_key = openai.api_key or read_file(os.path.dirname(os.path.abspath(__file__)) + "\\api_key.txt")
        self.rooms = list(rooms.items()) if rooms is not None else list(Schedule.ROOMS.items())
        self.max_tokens = 500
        # self.model = "gpt-3.5-turbo"
        # self.model = "gpt-4-turbo-preview"
        self.model = "gpt-4o"
        self.user:User = user
    
    @property
    def user_sesssions(self):
        user_sessions = self.user.sessions
        user_sessions = sorted(user_sessions, key=lambda session: session.room)
        return user_sessions

    def get_prompt(self):
        # TODO: assign a session limit
        
        # we get the rooms as a string
        rooms = ", ".join([f"{room[0]} - {room[1]}" for room in self.rooms])

        # we'll get a list of upcoming dates excluding today
        now = datetime.now()
        upcoming_dates = [now + timedelta(days=i) for i in range(1, 8)]
        # find the next Saturday and Sunday
        for i, date in enumerate(upcoming_dates):
            if date.weekday() == 5:
                saturday = date.strftime("%Y-%m-%d")
            elif date.weekday() == 6:
                sunday = date.strftime("%Y-%m-%d")
        upcoming_dates.pop() # remove the last date

        # we sort them by room
        user_sessions = self.user_sesssions
        user_sessions = [
            {
                'session_id': index,
                'room_id': session.room,
                'start_date': datetime.fromtimestamp(session.start).strftime('%Y-%m-%d'),
                'start_time': datetime.fromtimestamp(session.start).strftime('%H:%M'),
                'duration': session.span
            }
            for index, session in enumerate(user_sessions)]

        context = (
            f"Rooms: {rooms}\n"
            f"Now: {now.strftime('%A %Y/%m/%d %H:%M')}\n"
            f"Upcoming dates: {', '.join([date.strftime('%A %Y/%m/%d') for date in upcoming_dates])}\n"
            f"User sessions: {json.dumps(user_sessions, indent=4)}\n"
        )
        prompt = (
            'You work for a sports center that has multiple rooms for different activities. These rooms need to be booked in advance.\n'
            'You will receive user messages containing the natural language description of how they want to modify their schedule.\n'
            'In addition to user messages, you will also be provided with context for interpreting these messages, such as the rooms and their IDs, the user\'s current schedule, and the current date and time.\n'
            'Your job is to identify sessions that should be added to the schedule, and sessions that should be removed; and describe them as JSON objects.\n'
            'Feel free to include an explanation of your reasoning before each session you identified.\n'
            '\n'
            'If you identify one or multiple sessions that should be added, you should describe each as a separate JSON object, with the following fields (leave out any that aren\'t explicitly or implicitly provided):\n'
            '- action (string): the action to be performed, should be "add".\n'
            '- room_id (int): the ID of the room where the session will take place.\n'
            '- start_date (string): the start date of the session in the format "YYYY-MM-DD".\n'
            '- start_time (string): the start time of the session in the format "HH:MM".\n'
            '- duration (int): the duration of the session in minutes.\n'
            '\n'
            'If you identify one or multiple sessions that should be removed, you should describe each as a separate JSON object, with the following fields:\n'
            '- action (string): the action to be performed, should be "remove".\n'
            '- session_id (int): the ID of the session to be removed.\n'
            '\n'
            'CONTEXT:\n'
            f"{context}\n"
            '\n'
            'EXAMPLE 1:\n'
            f'User input: I want to play {self.rooms[-1][1]} this weekend at 5pm, for 1h.\n'
            'Output:\n'
            f'I will add a session for Saturday, since it is the upcoming weekend, with a room_id of {self.rooms[-1][0]}, meaning it is a {self.rooms[-1][1]} session.\n'
            '{"action": "add", "room_id": ' + str(self.rooms[-1][0]) + ', "start_date": "' + saturday + '", "start_time": "17:00", "duration": 60}\n'
            f'I will also add a session for Sunday, since it is also a weekend, with a room_id of {self.rooms[-1][0]}, meaning it is a {self.rooms[-1][1]} session.\n'
            '{"action": "add", "room_id": ' + str(self.rooms[-1][0]) + ', "start_date": "' + sunday + '", "start_time": "17:00", "duration": 60}\n'
            '\n'
            'EXAMPLE 2:\n'
            'Suppose the user has the following sessions:\n'
            '{"session_id": 0, "room_id": ' + str(self.rooms[0][0]) + ', "start_date": "' + saturday + '", "start_time": "10:00", "duration": 60}' + '\n'
            '{"session_id": 1, "room_id": ' + str(self.rooms[0][0]+1) + ', "start_date": "' + saturday + '", "start_time": "12:00", "duration": 60}' + '\n'
            '{"session_id": 2, "room_id": ' + str(self.rooms[0][0]) + ', "start_date": "' + sunday + '", "start_time": "14:00", "duration": 60}' + '\n'
            f'User input: I want to cancel all my {self.rooms[0][1]} sessions.\n'
            'Output:\n'
            f'I will cancel the sessions with a room_id of {self.rooms[0][0]}, since they are {self.rooms[0][1]} sessions.\n'
            '{"action": "remove", "session_id": 0}\n'
            '{"action": "remove", "session_id": 2}\n'
            '\n'
            'EXAMPLE 3:\n'
            'Suppose the user has the following sessions:\n'
            '{"session_id": 0, "room_id": ' + str(self.rooms[0][0]) + ', "start_date": "' + saturday + '", "start_time": "10:00", "duration": 90}' + '\n'
            '{"session_id": 1, "room_id": ' + str(self.rooms[0][0]+1) + ', "start_date": "' + sunday + '", "start_time": "12:00", "duration": 120}' + '\n'
            f'User input: Move my upcoming {self.rooms[0][1]} session to 3pm.\n'
            'Output:\n'
            'I will first cancel your upcoming ' + self.rooms[0][1] + ' session, which is the one with a session_id of 0.\n'
            '{"action": "remove", "session_id": 0}\n'
            'I will add a session with the same details, but with a start_time of 15:00.\n'
            '{"action": "add", "room_id": ' + str(self.rooms[0][0]) + ', "start_date": "' + saturday + '", "start_time": "15:00", "duration": 90}\n'
            '\n'
        )
        return prompt

    def process_user_message(self, message):
        """Takes a user message containing the description the sessions to be scheduled, and returns the response from the language model as a string."""
        
        # start the conversation with a system message, describing the purpose of the chatbot
        system_msg = self.get_prompt()

        # Generate a response using a GPT language model
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": message},
            ],
            max_tokens=self.max_tokens
        )
        response_content = response.choices[0].message.content

        # save the interaction to a file
        interaction = f"# System Message\n{system_msg}\n# Input\n{message}\n\n# Output ({self.model})\n{response_content}"
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "interaction.md"), "w") as file:
            file.write(interaction)
        
        return response_content

    def parse_response(self, response_content:str):
        """Takes the response from the language model and returns a list of session dictionaries."""
        # extract the JSON objects from the response
        json_objects = extract_json_objects(response_content)
        return json_objects

    def segregate_sessions(self, sessions):
        """Segregates the sessions into sessions to add and sessions to remove."""
        sessions_to_add = [session for session in sessions if session.get("action") == "add"]
        sessions_to_remove = [session for session in sessions if session.get("action") == "remove"]
        return sessions_to_add, sessions_to_remove

    def try_get_session(self, sess_dict:dict):
        """Attempts to convert a session dictionary to a session object."""

        # check if the dict has an action field
        
        try:
            # check if the action is add
            if sess_dict["action"] == "add":
                # parse the fields
                room_id = int(sess_dict["room_id"])
                duration = int(sess_dict["duration"])
                start_time = datetime.strptime(sess_dict["start_time"], "%H:%M").time()

                # get the start_date
                if "start_date" in sess_dict: # parse the start date if it's present
                    start_date = datetime.strptime(sess_dict["start_date"], "%Y-%m-%d")
                else: # assume today or tommorow
                    now = datetime.datetime.now()
                    start_date = now.date()
                    if start_time < now.time():
                        start_date += timedelta(days=1)
            else: # the action is remove
                # get the session id
                session_id = int(sess_dict["session_id"])
                
                # get the user session with that index
                user_session:ScheduleItem = self.user_sesssions[session_id]
                return user_session
                

        except ValueError:
            return None
        
        # combine the start date and time
        start = datetime.combine(start_date, start_time)

        # create the session object
        sess = Session(start=start.timestamp(), span=duration, room=room_id)

        # check if the session has ended
        if sess.has_ended():
            return None

        # return the session object
        return sess

    def try_get_sessions(self, sess_dicts):
        """Attempts to convert a list of session dictionaries to a list of session objects."""
        sessions = [self.try_get_session(sess_dict) for sess_dict in sess_dicts]
        sessions = [sess for sess in sessions if sess is not None]
        return sessions

def full_test():
    # Test the SmartScheduler class
    while True:
        # take the user's message
        message = input("Describe the session(s) you wish to schedule: ")
        
        # process the message
        raw_response = smart_scheduler.process_user_message(message)
        print(f"RAW RESPONSE:\n{raw_response}\n")

        # parse the response
        session_dicts = smart_scheduler.parse_response(raw_response)
        print(f"PARSED RESPONSE:\n{json.dumps(session_dicts, indent=4)}\n")

        # segregate the sessions
        sessions_to_add, sessions_to_cancel = smart_scheduler.segregate_sessions(session_dicts)
        
        # convert the response to session objects
        sessions_to_add = [smart_scheduler.try_get_session(sess_dict) for sess_dict in sessions_to_add]
        sessions_to_add = [sess for sess in sessions_to_add if sess is not None] # remove None values (invalid sessions)
        sessions_to_cancel = [smart_scheduler.try_get_session(sess_dict) for sess_dict in sessions_to_cancel]
        sessions_to_cancel = [sess for sess in sessions_to_cancel if sess is not None] # remove None values (invalid sessions)

        # remove sessions that have already ended
        sessions_to_add = [session for session in sessions_to_add if not session.has_ended()]

        # remove sessions that conflict with other sessions in the sessions_to_add list, but keep the first one
        temp_sessions = list(sessions_to_add) # create a copy of the list
        sessions_to_add = [] # clear the list
        while temp_sessions:
            session = temp_sessions.pop(0) # get the first session
            # add the session back to the list
            sessions_to_add.append(session)

            # get the sessions that conflict with the current session
            conflicting_sessions = [sess for sess in temp_sessions if sess.conflicts_with(session)]
            # remove the conflicting sessions
            temp_sessions = [sess for sess in temp_sessions if sess not in conflicting_sessions]

        # remove sessions that conflict with the existing schedule
        for room in set(session.room for session in sessions_to_add):
            # get the existing schedule for the room
            schedule = [si.session for si in Schedule(room).schedule]
            schedule = [sess for sess in schedule if sess not in sessions_to_cancel]
            
            # remove sessions that conflict with the existing schedule
            sessions_to_add = [session for session in sessions_to_add if not any(session.conflicts_with(existing_session) for existing_session in schedule)]

        # group sessions_to_add and sessions_to_remove by room
        sessions_by_room = {}
        for session in sessions_to_add + sessions_to_cancel:
            sessions_by_room.setdefault(session.room, {"add": [], "cancel": []})
            if session in sessions_to_add:
                sessions_by_room[session.room]["add"].append(session)
            else:
                sessions_by_room[session.room]["cancel"].append(session)
        
        # for every room, display the schedule
        print(f"Displaying the preview for {len(sessions_to_add)} sessions...")
        for room_id, sessions in sessions_by_room.items():
            displayer = ScheduleDisplayer(Schedule(room_id))
            displayer.user_id = smart_scheduler.user.id
            displayer.sessions_to_add = sessions["add"]
            displayer.sessions_to_cancel = sessions["cancel"]
            file = displayer.display()
            os.startfile(file)

def json_test():
    # Test the SmartScheduler class
    while True:
        message = input("Describe the session(s) you wish to schedule: ")
        raw_response = smart_scheduler.process_user_message(message)
        print(f"RAW RESPONSE:\n{raw_response}")

        
        # we parse and print the response
        parsed_response = smart_scheduler.parse_response(raw_response)
        print("PARSED RESPONSE:")
        for sess_dict in parsed_response:
            print(sess_dict)

if __name__ == "__main__":
    # we create a SmartScheduler object
    smart_scheduler = SmartScheduler(User("50766180742"))
    
    # print(smart_scheduler.get_prompt())
    # full_test()
    json_test()
