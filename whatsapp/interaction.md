# System Message
You work for a sports center that has multiple rooms for different activities. These rooms need to be booked in advance.
You will receive user messages containing the natural language description of how they want to modify their schedule.
In addition to user messages, you will also be provided with context for interpreting these messages, such as the rooms and their IDs, the user's current schedule, and the current date and time.
Your job is to identify sessions that should be added to the schedule, and sessions that should be removed; and describe them as JSON objects.
Feel free to include an explanation of your reasoning before each session you identified.

If you identify one or multiple sessions that should be added, you should describe each as a separate JSON object, with the following fields (leave out any that aren't explicitly or implicitly provided):
- action (string): the action to be performed, should be "add".
- room_id (int): the ID of the room where the session will take place.
- start_date (string): the start date of the session in the format "YYYY-MM-DD".
- start_time (string): the start time of the session in the format "HH:MM".
- duration (int): the duration of the session in minutes.

If you identify one or multiple sessions that should be removed, you should describe each as a separate JSON object, with the following fields:
- action (string): the action to be performed, should be "remove".
- session_id (int): the ID of the session to be removed.

CONTEXT:
Rooms: 0 - Squash, 1 - Racquetball, 2 - Padel
Now: Saturday 2024/06/22 21:45
Upcoming dates: Sunday 2024/06/23, Monday 2024/06/24, Tuesday 2024/06/25, Wednesday 2024/06/26, Thursday 2024/06/27, Friday 2024/06/28
User sessions: []


EXAMPLE 1:
User input: I want to play Padel this weekend at 5pm, for 1h.
Output:
I will add a session for Saturday, since it is the upcoming weekend, with a room_id of 2, meaning it is a Padel session.
{"action": "add", "room_id": 2, "start_date": "2024-06-29", "start_time": "17:00", "duration": 60}
I will also add a session for Sunday, since it is also a weekend, with a room_id of 2, meaning it is a Padel session.
{"action": "add", "room_id": 2, "start_date": "2024-06-23", "start_time": "17:00", "duration": 60}

EXAMPLE 2:
Suppose the user has the following sessions:
{"session_id": 0, "room_id": 0, "start_date": "2024-06-29", "start_time": "10:00", "duration": 60}
{"session_id": 1, "room_id": 1, "start_date": "2024-06-29", "start_time": "12:00", "duration": 60}
{"session_id": 2, "room_id": 0, "start_date": "2024-06-23", "start_time": "14:00", "duration": 60}
User input: I want to cancel all my Squash sessions.
Output:
I will cancel the sessions with a room_id of 0, since they are Squash sessions.
{"action": "remove", "session_id": 0}
{"action": "remove", "session_id": 2}

EXAMPLE 3:
Suppose the user has the following sessions:
{"session_id": 0, "room_id": 0, "start_date": "2024-06-29", "start_time": "10:00", "duration": 90}
{"session_id": 1, "room_id": 1, "start_date": "2024-06-23", "start_time": "12:00", "duration": 120}
User input: Move my upcoming Squash session to 3pm.
Output:
I will first cancel your upcoming Squash session, which is the one with a session_id of 0.
{"action": "remove", "session_id": 0}
I will add a session with the same details, but with a start_time of 15:00.
{"action": "add", "room_id": 0, "start_date": "2024-06-29", "start_time": "15:00", "duration": 90}


# Input
I want to play Padel on weekdays from 6 to 7:30p. Except on Thursday, I'm busy that day.

# Output (gpt-4o)
The user wants to book Padel sessions (room_id: 2) on weekdays (Monday to Friday) from 6:00 PM to 7:30 PM (90 minutes), except Thursday. 

Here is the breakdown of the sessions to be added:

- Monday 2024-06-24
- Tuesday 2024-06-25
- Wednesday 2024-06-26
- Friday 2024-06-28

```json
[
    {"action": "add", "room_id": 2, "start_date": "2024-06-24", "start_time": "18:00", "duration": 90},
    {"action": "add", "room_id": 2, "start_date": "2024-06-25", "start_time": "18:00", "duration": 90},
    {"action": "add", "room_id": 2, "start_date": "2024-06-26", "start_time": "18:00", "duration": 90},
    {"action": "add", "room_id": 2, "start_date": "2024-06-28", "start_time": "18:00", "duration": 90}
]
```

Explanation:
- Each session is specified to be added to room 2 (Padel).
- The start date for each session is one of the specified weekdays.
- The start time for each session is 18:00 (6:00 PM).
- The duration is 90 minutes as requested by the user.