import json
import traceback
import os
import wapp_agent
from wapp_agent import WAppAgent
from convo import Convo
import asyncio
from datetime import datetime, timezone, timedelta
from session import Session, Timestamp
from schedule import Schedule, ScheduleDisplayer, ScheduleItem
from user import User, UserManager
from smart_scheduler import SmartScheduler
from schedule_edit import ScheduleEdit

agent = WAppAgent(
    "https://graph.facebook.com/v18.0",
    open(os.path.dirname(os.path.abspath(__file__))+'\\token.txt', 'r').read(),
    "12345678",
    "109825938838824"
)

def get_day_list():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    dayDts = [today + timedelta(days=i) for i in range(9)]
    dayTexts = [d.strftime("%a, %b %d") for d in dayDts]
    dayTexts[0] += " (Today)"
    dayTexts[1] += " (Tomorrow)"
    return dayDts,dayTexts

# Define the rooms
Schedule.ROOMS = {0: "Squash", 1: "Racquetball", 2: "Padel"}

# programatically create the room schedules
room_schedules = {room_name: Schedule(room_id) for room_id, room_name in Schedule.ROOMS.items()}

cost_per_minute = 1

async def handle_conversation(convo: Convo):
    # HELPER FUNCTIONS
    def create_options(header, prompt, options, button = "Select"):
        return wapp_agent.build_interactive(
            body=prompt,
            header=header,
            # footer="Answer using the options below",
            interactive=wapp_agent.create_interactive_list(button, options))
    
    def create_buttons(header, prompt, buttons):
        return wapp_agent.build_interactive(
            body=prompt,
            header=header,
            # footer="Answer using the buttons below",
            interactive=wapp_agent.create_interactive_buttons(buttons))

    async def send_room_schedule(schedule, to_add=None, to_cancel=None):
        # we configure the ScheduleDisplayer
        displayer = ScheduleDisplayer(schedule)
        displayer.user_id = convo.user_id
        if to_add:
            displayer.sessions_to_add = list(to_add)
        if to_cancel:
            displayer.sessions_to_cancel = list(to_cancel)

        # we display the schedule
        file = displayer.display()

        # we send the schedule
        media_id = await agent.upload_media(file)
        await convo.send_message(wapp_agent.build_media(media_id))
        await asyncio.sleep(1) # sleep to allow the media to arrive before sending the next message

    # MENU FUNCTIONS
    async def schedule_session(instant = False):
        sess: Session = None
        session_str = "*Session info*:\n"
        schedule:Schedule = None

        def create_session_options(prompt, options, button = "Select"):
            return create_options("Schedule session", session_str + "\n" + prompt, options, button)

        # we prompt the user to select a room
        rooms = list(room_schedules.keys())
        reply = (await convo.prompt(create_session_options("*Select a room*", rooms + ["Cancel"]))).text
        if reply not in rooms: return
        room = rooms.index(reply)
        session_str += f"*Room*: _{reply}_\n"
        schedule = room_schedules[rooms[room]]

        # we send the room's schedule
        await send_room_schedule(schedule)

        # we prompt the user to select a span
        durations = list(range(15, 121, 15))
        durationTexts = [f"{d // 60}h {d % 60:02d}m (${d*cost_per_minute})" for d in durations]
        reply = (await convo.prompt(create_session_options("*How long will the session be?*", durationTexts + ["Cancel"]))).text
        if reply not in durationTexts: return
        duration = durations[durationTexts.index(reply)]
        cost = duration * cost_per_minute
        session_str += f"*Duration*: _{reply}_\n"
        session_str += f"*Cost*: _${cost}_\n"
        
        # check if the user can afford the session
        if user.credits < cost:
            await convo.send_message("You don't have enough credits to schedule this session")
            return

        if not instant:
            # TODO: show only the available times (meaning, the times that are not already taken by other sessions; and the times that are not in the past)
            # prompt the user to select a day
            dayDts, dayTexts = get_day_list()
            reply = (await convo.prompt(create_session_options("*Select a day*", dayTexts + ["Cancel"]))).text
            if reply not in dayTexts: return
            start = dayDts[dayTexts.index(reply)]
            session_str += f"*Date*: _{reply}_\n"
            
            # we prompt the user to select a time of day
            now = datetime.now().hour if start.date() == datetime.now().date() else 0 # if the selected day is today, we start from the current hour, otherwise we start from 00h
            times_of_day = (["Early hours (00h - 07h)"] if now < 8 else []) + (["Midday (08h - 15h)"] if now < 16 else []) + ["Evening (16h - 23h)"]
            reply = (await convo.prompt(create_session_options("*Select a time of day*", times_of_day + ["Cancel"]))).text
            if reply not in times_of_day: return
            tod = 3 - (len(times_of_day) - times_of_day.index(reply))

            # we prompt the user to select an hour
            hours = [f"{(tod*8)+i:02d}h" for i in range(8) if ((tod*8)+i) >= now]
            reply = (await convo.prompt(create_session_options(f"*Select an hour*", hours + ["Cancel"]))).text
            if reply not in hours: return
            start = start.replace(hour=int(reply[:2]))
            session_str += f"*Time*: _{start.hour:02d}:00_\n"

            # we prompt the user to select a minute
            minutes = [0, 10, 15, 20, 30, 40, 45, 50]
            now = datetime.now().minute if start.date() == datetime.now().date() and start.hour == datetime.now().hour else 0 # if the selected day and hour are today and now, we start from the current minute, otherwise we start from 00m
            now = max([m for m in minutes if m <= now], default=0)
            minutes = [f'{m}' for m in minutes if m >= now]
            reply = (await convo.prompt(create_session_options("*Select a minute*", minutes + ["Cancel"]))).text
            if reply not in minutes: return
            start = start.replace(minute=int(reply))
            session_str = '\n'.join(session_str.split('\n')[:-2]) + f"\n*Time*: _{start.hour:02d}:{start.minute:02d}_\n"

            # we instantiate the Session object
            sess = Session(start.timestamp(), duration, room)

        else:
            # we instantiate the Session object, using the current time as the start time
            start = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
            sess = Session(start.timestamp(), duration, room)
            session_str += f"*Time*: _{sess.start.format('%H:%M')}_\n"
        
        if schedule.is_available(sess):
            sch_item = ScheduleItem.from_session(sess, convo.user_id)

            # we send the room's schedule with the session previewed
            await send_room_schedule(schedule, to_add=[sess])

            # we prompt the user to confirm the session
            btns = wapp_agent.create_interactive_buttons(["Yes", "No"])
            msg = wapp_agent.build_interactive(
                header="Schedule session",
                body=f"{session_str}\n*Confirm the session?*" + (f"\nKeep in mind since the session starts in less than {Schedule.CANCEL_DEADLINE_MINS} minutes, you won't be able to cancel it after confirmation." if sch_item.past_deadline() else ""),
                footer="Answer using the buttons below",
                interactive=btns)
            reply = (await convo.prompt(msg)).text
        
            if reply == "Yes":
                # we add the session to the schedule
                edit = ScheduleEdit(user, sessions_to_add=[sess])
                edit.apply_all_filters()
                saved = edit.book_sessions()
                if saved:
                    confirmation_msg = f"Session scheduled\n"
                    if sch_item.past_deadline():
                        confirmation_msg += f"*Passcode*: _{sess.passcode}_"
                    else:
                        confirmation_msg += f"Your session's passcode will be available {Schedule.CANCEL_DEADLINE_MINS} minutes before the session starts."
                    await convo.send_message(confirmation_msg)
        else:
            await convo.send_message("Session not scheduled\nThe selected time is already taken")

    async def view_schedule():
        # Prompt the user to choose a room to view its schedule
        rooms = list(room_schedules.keys())
        reply = (await convo.prompt(create_options("View schedule", "*Select a room*", rooms + ["Cancel"]))).text
        if reply not in rooms: return

        schedule = room_schedules[reply]
        
        # Send the room's schedule
        await send_room_schedule(schedule)

    async def cancel_session():
        # we get the user's sessions in all rooms
        sessionItems = Schedule.get_user_schedule(convo.user_id)
        
        # we filter the sessions that haven't passed their cancellation deadline
        sessionItems = [s for s in sessionItems if not s.past_deadline()]
        sessionItems = sessionItems[:9] # we limit the number of sessions to display to 9

        # we check if the user has any sessions available for cancellation
        if len(sessionItems) == 0:
            await convo.send_message("You don't have any scheduled sessions available for cancellation")
        else:
            # we prompt the user to select the session they wish to remove
            session_strs = [s.session.start.format("%a, %b %d %H:%M") for s in sessionItems]
            reply = (await convo.prompt(create_options(
                "Cancel session",
                "*Select a session to cancel*" + f"\nKeep in mind that the deadline for cancellations is {Schedule.CANCEL_DEADLINE_MINS} minutes before the session starts.",
                session_strs + ["Go back"]))).text
            if reply not in session_strs: return
            sessionItem = sessionItems[session_strs.index(reply)]
            session = sessionItem.session

            # we send the room's schedule with the session to cancel highlighted
            schedule = room_schedules[list(room_schedules.keys())[session.room]]
            await send_room_schedule(schedule, to_cancel=[session])

            # we prompt the user to confirm the cancellation
            btns = wapp_agent.create_interactive_buttons(["Yes", "No"])
            msg = wapp_agent.build_interactive(
                header="Cancel session",
                body=f"*Session info*:\n*Room*: _{list(room_schedules.keys())[session.room]}_\n*Time*: _{session.start.format('%a, %b %d %H:%M')}_\n*Confirm the cancellation?*",
                footer="Answer using the buttons below",
                interactive=btns)
            reply = (await convo.prompt(msg)).text

            if reply == "Yes":
                if sessionItem.past_deadline():
                    await convo.send_message("Session not cancelled\nThe deadline for cancellations has passed")
                    return
                
                # we remove the session from the schedule
                edit = ScheduleEdit(user, sessions_to_cancel=[session])
                edit.apply_all_filters()
                cancelled = edit.cancel_sessions()


                # we send a confirmation message
                if cancelled:
                    await convo.send_message(f"Session cancelled\n*Refund*: _${edit.cancellation_refund}_")
                else:
                    await convo.send_message("Session not cancelled.\nIt may have already been cancelled or the session's cancellation deadline may have passed.'")

    async def add_credits():
        # we prompt the user to input the amount of credits to add
        btns = wapp_agent.create_interactive_buttons(["Cancel"])
        msg = wapp_agent.build_interactive(
            header="Add credits",
            body=f"Enter the amount of credits to add",
            interactive=btns)
        reply = (await convo.prompt(msg)).text
        try:
            amount = int(reply)
        except ValueError:
            return

        # we add the credits to the user
        user.credits += amount
        await convo.send_message(f"Added {amount} credits\nNew balance: ${user.credits}")

    async def smart_schedule():
        async def report_filtered_sessions(filtered_sessions_count, message_templ):
            if filtered_sessions_count:
                await convo.send_message(message_templ.format(filtered_sessions_count))

        smart_sch = SmartScheduler(user=user)

        # set up a loop
        while True:
            # take the user's message
            user_prompt = create_buttons("Smart schedule", "Describe the session(s) you wish to schedule\nMake sure to include the room, date, time and duration.", ["Cancel"])
            user_input = (await convo.prompt(user_prompt)).text
            if user_input == "Cancel":
                return
            await convo.send_message("Message received. Processing...")

            # process the message
            raw_response = smart_sch.process_user_message(user_input)
            print(f"RAW RESPONSE:\n{raw_response}\n")

            # parse the response
            session_dicts = smart_sch.parse_response(raw_response)
            print(f"PARSED RESPONSE:\n{json.dumps(session_dicts, indent=4)}\n")
            
            # segregate the sessions
            ss_to_add, ss_to_cancel = smart_sch.segregate_sessions(session_dicts)

            # convert the response to session objects, and load it into the ScheduleEdit object
            schedule_edit = ScheduleEdit(
                sessions_to_add=smart_sch.try_get_sessions(ss_to_add),
                sessions_to_cancel=smart_sch.try_get_sessions(ss_to_cancel),
                user=user)
            await report_filtered_sessions(len(ss_to_add) - len(schedule_edit.sessions_to_add), "{} session(s) could not be scheduled due to invalid input.")
            await report_filtered_sessions(len(ss_to_cancel) - len(schedule_edit.sessions_to_cancel), "{} session(s) could not be cancelled due to invalid input.")

            # remove sessions_to_cancel that have already passed their cancellation deadline
            await report_filtered_sessions(len(schedule_edit.filter_past_deadline()), "{} session(s) could not be cancelled due to the sessions having already passed their cancellation deadline.")

            # remove sessions that have already ended
            await report_filtered_sessions(len(schedule_edit.filter_ended()), "{} session(s) could not be scheduled due to the sessions having already ended.")

            # remove conflicting sessions
            await report_filtered_sessions(len(schedule_edit.filter_conflicting()), "{} session(s) could not be scheduled due to conflicts.")

            # remove sessions that the user wouldn't be able to afford
            await report_filtered_sessions(len(schedule_edit.filter_unaffordable()), "{} session(s) could not be scheduled due to insufficient credits.")

            # check if there are any valid changes to make to the schedule
            if len(schedule_edit.all_sessions) == 0:
                await convo.send_message("No valid changes to make to the schedule. Please try again.")
                continue
            
            # group sessions_to_add and sessions_to_remove by room
            sessions_by_room = schedule_edit.group_by_room()
            
            # we display the schedule
            print(f"Displaying the preview for {len(ss_to_add)} sessions...")
            for room_id, sessions in sessions_by_room.items():
                # we display the sessions to be scheduled as text
                to_add_str = '\n'.join([f"{session.start.format('%a, %b %d %H:%M')} ({session.span} minutes)" for session in sessions["add"]])
                to_cancel_str = '\n'.join([f"{session.start.format('%a, %b %d %H:%M')} ({session.span} minutes)" for session in sessions["cancel"]])
                await convo.send_message(f"*Room*: {Schedule.ROOMS[room_id]}\n" + (f"\n*Sessions to add:*\n{to_add_str}\n" if to_add_str else "") + (f"\n*Sessions to cancel:*\n{to_cancel_str}\n" if to_cancel_str else ""))

                # we display the schedule visually
                await send_room_schedule(
                    schedule=Schedule(room_id),
                    to_add=sessions["add"],
                    to_cancel=sessions["cancel"]
                )

            # we prompt the user to confirm the schedule
            user_input = create_buttons("Smart schedule", f"*Net cost*: _${schedule_edit.net_cost}_\nConfirm the schedule?", ["Yes", "Retry", "Cancel"])
            reply = (await convo.prompt(user_input)).text
            if reply == "Cancel":
                return
            if reply == "Yes":
                # we remove the sessions from the schedule
                cancelled = schedule_edit.cancel_sessions()

                # we add the sessions to the schedule
                saved = schedule_edit.book_sessions()
                
                # we send a confirmation message
                await convo.send_message(f"{len(saved)} session(s) scheduled\n{len(cancelled)} session(s) cancelled\n*Net cost*: _${schedule_edit.net_cost}_\n*New balance*: _${user.credits}_")
                return

    # MAIN
    def get_menu():
        # Define the main menu
        optn_list = wapp_agent.create_interactive_list("Select", list(menu_optns.keys()))
        user_sessions = Schedule.get_user_schedule(convo.user_id)
        upcoming_session:ScheduleItem = next(iter([si for si in user_sessions if si.past_deadline()]), None) # get the first upcoming session if there is one

        # we get the status of the user's sessions
        sessions_status = f"No upcoming sessions in the next {Schedule.CANCEL_DEADLINE_MINS} minutes"
        if upcoming_session is not None:
            sessions_status = (
                f"*{'Current' if upcoming_session.session.has_started() else 'Upcoming'} session*:\n"
                f"  *Start*: _{upcoming_session.session.start.format('%a, %b %d %H:%M')}_\n"
                f"  *Room*: _{list(room_schedules.keys())[upcoming_session.session.room]}_\n"
                f"  *Duration*: _{upcoming_session.session.span} minutes_\n"
                f"  *Passcode*: _{upcoming_session.session.passcode}_\n"
            )

        menu_msg = wapp_agent.build_interactive(
            body=f"*Account balance*: _${user.credits}_\n"
                 +sessions_status+"\n"
                 +"What do you want to do?"
            ,
            header="Main Menu",
            interactive=optn_list)
        return menu_msg

    menu_optns = {
        "Schedule session 📆": schedule_session,
        "Instant session 🏃‍♂️": lambda: schedule_session(True),
        "Cancel session ❌": cancel_session,
        "View schedule 📅": view_schedule,
        "Add credits 💰": add_credits,
        "Smart schedule 🤖": smart_schedule
    }

    # attempt to create a user for this conversation
    user = User(convo.user_id)

    # Start the conversation loop
    while True:
        try:
            msg = await convo.wait_for_message()
            if msg.text in menu_optns:
                await menu_optns[msg.text]()
            await convo.send_message(get_menu())
        except Exception as e:
            traceback.print_exc()
            print(e)

asyncio.run(Convo.setup_agent(agent, handle_conversation))