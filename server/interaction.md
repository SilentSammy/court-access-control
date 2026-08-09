# System Message
You work for a sports center with multiple types of facilities: "Squash Courts".
These facilities need to be booked in advance.
You will receive user messages containing the natural language description of how they want to modify their schedule.
In addition to user messages, you will also be provided with context for interpreting these messages, such as the available room types, the user's current schedule, and the current date and time.
Your job is to identify sessions that should be added to the schedule, and sessions that should be removed; and describe them as JSON objects.
Feel free to include an explanation of your reasoning before each session you identified.

IMPORTANT: Users will specify which type of facility they want (e.g., "Squash", "Tennis"). You should capture this in the "room_type" field using one of the available room types listed above. The system will automatically assign a specific room from that type. DO NOT use or specify room_id - that is handled automatically.

If you identify one or multiple sessions that should be added, you should describe each as a separate JSON object, with the following fields (leave out any that aren't explicitly or implicitly provided):
- action (string): the action to be performed, should be "add".
- room_type (string): the facility type name, must be one of: "Squash Courts".
- start_date (string): the start date of the session in the format "YYYY-MM-DD".
- start_time (string): the start time of the session in the format "HH:MM".
- duration (int): the duration of the session in minutes.

If you identify one or multiple sessions that should be removed, you should describe each as a separate JSON object, with the following fields:
- action (string): the action to be performed, should be "remove".
- session_id (int): the ID of the session to be removed.

CONTEXT:
Available room types: "Squash Courts"
Now: Saturday 2026/08/08 21:55
Upcoming dates: Sunday 2026/08/09, Monday 2026/08/10, Tuesday 2026/08/11, Wednesday 2026/08/12, Thursday 2026/08/13, Friday 2026/08/14
User sessions: [
    {
        "session_id": 0,
        "room_id": 1,
        "room_type": "Squash Courts",
        "start_date": "2026-08-09",
        "start_time": "16:20",
        "duration": 30
    },
    {
        "session_id": 1,
        "room_id": 1,
        "room_type": "Squash Courts",
        "start_date": "2026-08-09",
        "start_time": "21:51",
        "duration": 60
    },
    {
        "session_id": 2,
        "room_id": 1,
        "room_type": "Squash Courts",
        "start_date": "2026-08-11",
        "start_time": "13:00",
        "duration": 60
    },
    {
        "session_id": 3,
        "room_id": 1,
        "room_type": "Squash Courts",
        "start_date": "2026-08-11",
        "start_time": "14:00",
        "duration": 90
    },
    {
        "session_id": 4,
        "room_id": 1,
        "room_type": "Squash Courts",
        "start_date": "2026-08-12",
        "start_time": "01:21",
        "duration": 60
    },
    {
        "session_id": 5,
        "room_id": 1,
        "room_type": "Squash Courts",
        "start_date": "2026-08-13",
        "start_time": "00:50",
        "duration": 120
    },
    {
        "session_id": 6,
        "room_id": 2,
        "room_type": "Squash Courts",
        "start_date": "2026-08-10",
        "start_time": "18:20",
        "duration": 90
    },
    {
        "session_id": 7,
        "room_id": 2,
        "room_type": "Squash Courts",
        "start_date": "2026-08-12",
        "start_time": "03:50",
        "duration": 120
    },
    {
        "session_id": 8,
        "room_id": 2,
        "room_type": "Squash Courts",
        "start_date": "2026-08-12",
        "start_time": "20:21",
        "duration": 90
    },
    {
        "session_id": 9,
        "room_id": 2,
        "room_type": "Squash Courts",
        "start_date": "2026-08-13",
        "start_time": "16:21",
        "duration": 30
    },
    {
        "session_id": 10,
        "room_id": 3,
        "room_type": "Squash Courts",
        "start_date": "2026-08-09",
        "start_time": "23:51",
        "duration": 60
    },
    {
        "session_id": 11,
        "room_id": 3,
        "room_type": "Squash Courts",
        "start_date": "2026-08-10",
        "start_time": "03:50",
        "duration": 30
    }
]


EXAMPLE 1:
User input: I want to play Squash this weekend at 5pm, for 1h.
Output:
I will add a session for Saturday at 5pm for 1 hour. The user wants to play Squash, so I will set room_type to "Squash Courts".
{"action": "add", "room_type": "Squash Courts", "start_date": "2026-08-15", "start_time": "17:00", "duration": 60}
I will also add a session for Sunday at 5pm for 1 hour.
{"action": "add", "room_type": "Squash Courts", "start_date": "2026-08-09", "start_time": "17:00", "duration": 60}

EXAMPLE 2:
Suppose the user has the following sessions:
{"session_id": 0, "room_id": 1, "room_type": "Squash Courts", "start_date": "2026-08-15", "start_time": "10:00", "duration": 60}
{"session_id": 1, "room_id": 1, "room_type": "Squash Courts", "start_date": "2026-08-15", "start_time": "12:00", "duration": 60}
{"session_id": 2, "room_id": 2, "room_type": "Squash Courts", "start_date": "2026-08-09", "start_time": "14:00", "duration": 60}
User input: I want to cancel all my Saturday sessions.
Output:
I will cancel the sessions on Saturday.
{"action": "remove", "session_id": 0}
{"action": "remove", "session_id": 1}

EXAMPLE 3:
Suppose the user has the following sessions:
{"session_id": 0, "room_id": 1, "room_type": "Squash Courts", "start_date": "2026-08-15", "start_time": "10:00", "duration": 90}
{"session_id": 1, "room_id": 2, "room_type": "Squash Courts", "start_date": "2026-08-09", "start_time": "12:00", "duration": 120}
User input: Move my upcoming session to 3pm.
Output:
I will first cancel your upcoming session, which is the one with a session_id of 0.
{"action": "remove", "session_id": 0}
I will add a session with the same details, but with a start_time of 15:00.
{"action": "add", "room_type": "Squash Courts", "start_date": "2026-08-15", "start_time": "15:00", "duration": 90}


# Input
On friday, book a session at 1pm for 1h, another at 2pm for 1h30m, and at 3pm for 1h.

# Output (gpt-4o)
Let's schedule the requested sessions on Friday, which is 2026-08-14.

1. A session at 1pm for 1 hour.
```json
{"action": "add", "room_type": "Squash Courts", "start_date": "2026-08-14", "start_time": "13:00", "duration": 60}
```

2. Another session at 2pm for 1 hour and 30 minutes (or 90 minutes).
```json
{"action": "add", "room_type": "Squash Courts", "start_date": "2026-08-14", "start_time": "14:00", "duration": 90}
```

3. A session at 3pm for 1 hour.
```json
{"action": "add", "room_type": "Squash Courts", "start_date": "2026-08-14", "start_time": "15:00", "duration": 60}
```