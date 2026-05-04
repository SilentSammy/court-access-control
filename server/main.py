import os
import traceback
import wapp_agent as wapp_agent
from wapp_agent import WAppAgent, Convo
import asyncio
from facility import FacilityManager
from device_discoverer import DeviceDiscoverer
from session_manager import SessionManager
from session import Session, Timestamp
from datetime import datetime, timedelta
from user import User
from schedule import Schedule, ScheduleDisplayer, ScheduleItem
from schedule_edit import ScheduleEdit, COST_PER_MINUTE

# SETUP
facility = FacilityManager(
    discoverer=DeviceDiscoverer(
        discovery_interval=30,
        health_check_interval=10,
        scan_networks=[
            "192.168.137.0/24",  # Windows hotspot
            "192.168.1.0/24"     # Home network (UPDATE: check ipconfig at home for your actual network)
        ]
    ),
    mock_rooms=["1", "2", "3"]  # Always available for scheduling even without physical devices
)
session_manager = SessionManager(check_interval=5, sessions_file="sessions.txt")
agent = WAppAgent(config_file=os.path.dirname(os.path.abspath(__file__))+'\\wapp.json')
# Timestamp.enable_test_mode()  # Enable test mode for faster session testing

# Room groups: maps a sport/court label to a list of room ID strings.
# When a user books, the system auto-assigns the first available room in the group.
ROOM_GROUPS = {
    'Squash': ['1', '2', '3'],
}

async def handle_conversation(convo: Convo):
    def get_room_ids():
        """Get available room IDs (discovered devices + mock_rooms)."""
        return facility.get_room_ids()
    
    def create_menu_options(options):
        """Helper to create interactive list."""
        return wapp_agent.create_interactive_list("Select", options)

    async def prompt_or_auto_select(header, body, options, cancel_label="Cancel"):
        """If only one non-cancel option exists, return it automatically.
        Otherwise prompt the user normally. Always returns the selected text."""
        real_options = [o for o in options if o != cancel_label]
        if len(real_options) == 1:
            return real_options[0]
        msg = wapp_agent.build_interactive(
            header=header,
            body=body,
            interactive=create_menu_options(options)
        )
        reply = await convo.prompt(msg)
        return reply.text

    user = User(convo.user_id)

    def update_room_registry():
        """Sync Schedule.ROOMS with currently discovered rooms."""
        for rid in get_room_ids():
            int_id = int(rid)
            if int_id not in Schedule.ROOMS:
                Schedule.ROOMS[int_id] = rid

    def get_group_names():
        """Return list of group/court-type names."""
        return list(ROOM_GROUPS.keys())

    def get_group_rooms(group_name):
        """Return room ID strings for a group (handles int or str IDs)."""
        return [str(r) for r in ROOM_GROUPS.get(group_name, [])]

    def get_room_group(room_id):
        """Return the most encompassing group name for a room_id (the one with the most rooms),
        or None if not listed in any group."""
        matches = [
            (name, rooms) for name, rooms in ROOM_GROUPS.items()
            if str(room_id) in [str(r) for r in rooms]
        ]
        if not matches:
            return None
        return max(matches, key=lambda x: len(x[1]))[0]

    async def send_room_schedule(schedule, to_add=None, to_cancel=None):
        """Send a visual schedule image for the given room."""
        update_room_registry()
        displayer = ScheduleDisplayer(schedule)
        displayer.user_id = convo.user_id
        if to_add:
            displayer.sessions_to_add = list(to_add)
        if to_cancel:
            displayer.sessions_to_cancel = list(to_cancel)
        file = displayer.display()
        media_id = await agent.upload_media(file)
        await convo.send_message(wapp_agent.build_media(media_id))
        await asyncio.sleep(1)

    async def send_group_schedule(group_name, to_add=None, to_cancel=None):
        """Send a merged schedule image for all rooms in a group (sub-column layout)."""
        update_room_registry()
        room_ids = get_group_rooms(group_name)
        schedules = [Schedule(int(rid)) for rid in room_ids]
        displayer = ScheduleDisplayer(schedules)
        displayer.title = group_name
        displayer.user_id = convo.user_id
        if to_add:
            displayer.sessions_to_add = list(to_add)
        if to_cancel:
            displayer.sessions_to_cancel = list(to_cancel)
        file = displayer.display()
        media_id = await agent.upload_media(file)
        await convo.send_message(wapp_agent.build_media(media_id))
        await asyncio.sleep(1)

    # ===== USER FEATURES =====
    async def user_schedule_session():
        """User: book a timed session — grouped courts are auto-assigned."""
        update_room_registry()
        group_names = get_group_names()
        choices = group_names
        if not choices:
            await convo.send_message("⚠️ No rooms available yet. Please wait...")
            return

        session_str = "*Session info*:\n"

        # Step 1: Court type (group) or individual room
        selected = await prompt_or_auto_select(
            "Schedule Session",
            session_str + "\n*Select a court type*",
            choices + ["Cancel"]
        )
        if selected == "Cancel" or selected not in choices:
            return
        is_group = selected in group_names
        if is_group:
            group_name = selected
            group_room_ids = get_group_rooms(group_name)
            session_str += f"*Court type*: _{group_name}_\n"
            await send_group_schedule(group_name)
        else:
            group_name = None
            room_id_str = selected
            room_id_int = int(room_id_str)
            session_str += f"*Room*: _{room_id_str}_\n"
            await send_room_schedule(Schedule(room_id_int))

        # Step 2: Duration
        durations = list(range(15, 121, 15))
        duration_texts = [
            (f"{d // 60}h {d % 60:02d}m" if d >= 60 else f"{d}m") + f" (${d * COST_PER_MINUTE})"
            for d in durations
        ]
        msg = wapp_agent.build_interactive(
            header="Schedule Session",
            body=session_str + "\n*Select duration*",
            interactive=create_menu_options(duration_texts + ["Cancel"])
        )
        reply = await convo.prompt(msg)
        if reply.text == "Cancel" or reply.text not in duration_texts:
            return
        duration = durations[duration_texts.index(reply.text)]
        cost = duration * COST_PER_MINUTE
        session_str += f"*Duration*: _{reply.text}_\n"
        session_str += f"*Cost*: _${cost}_\n"

        # Check credits
        if user.credits < cost:
            await convo.send_message(
                f"❌ Insufficient credits\n"
                f"*Required*: ${cost}\n"
                f"*Your balance*: ${user.credits}"
            )
            return

        # Step 3: Day
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        day_dts = [today + timedelta(days=i) for i in range(9)]
        day_texts = [d.strftime("%a, %b %d") for d in day_dts]
        day_texts[0] += " (Today)"
        day_texts[1] += " (Tomorrow)"
        msg = wapp_agent.build_interactive(
            header="Schedule Session",
            body=session_str + "\n*Select a day*",
            interactive=create_menu_options(day_texts + ["Cancel"])
        )
        reply = await convo.prompt(msg)
        if reply.text == "Cancel" or reply.text not in day_texts:
            return
        start = day_dts[day_texts.index(reply.text)]
        session_str += f"*Date*: _{reply.text}_\n"

        # Step 4: Time of day
        now_hour = datetime.now().hour if start.date() == datetime.now().date() else 0
        all_slots = ["Early hours (00h - 07h)", "Midday (08h - 15h)", "Evening (16h - 23h)"]
        time_slots = [s for s in all_slots if all_slots.index(s) * 8 + 7 >= now_hour]
        selected_slot = await prompt_or_auto_select(
            "Schedule Session",
            session_str + "\n*Select a time of day*",
            time_slots + ["Cancel"]
        )
        if selected_slot == "Cancel" or selected_slot not in time_slots:
            return
        tod_index = all_slots.index(selected_slot)

        # Step 5: Hour
        hours = [f"{(tod_index * 8) + i:02d}h" for i in range(8) if (tod_index * 8 + i) >= now_hour]
        selected_hour = await prompt_or_auto_select(
            "Schedule Session",
            session_str + "\n*Select an hour*",
            hours + ["Cancel"]
        )
        if selected_hour == "Cancel" or selected_hour not in hours:
            return
        start = start.replace(hour=int(selected_hour[:2]))

        # Step 6: Minute
        minute_opts = [0, 10, 15, 20, 30, 40, 45, 50]
        now_minute = (
            datetime.now().minute
            if start.date() == datetime.now().date() and start.hour == datetime.now().hour
            else 0
        )
        now_minute = max((m for m in minute_opts if m <= now_minute), default=0)
        minute_texts = [f"{m:02d}" for m in minute_opts if m >= now_minute]
        msg = wapp_agent.build_interactive(
            header="Schedule Session",
            body=session_str + "\n*Select minutes*",
            interactive=create_menu_options(minute_texts + ["Cancel"])
        )
        reply = await convo.prompt(msg)
        if reply.text == "Cancel" or reply.text not in minute_texts:
            return
        start = start.replace(minute=int(reply.text))
        session_str = "\n".join(session_str.splitlines()[:-2]) + f"\n*Time*: _{start.hour:02d}:{start.minute:02d}_\n"

        # Build and validate the session
        if is_group:
            sess = Schedule.find_available_room(group_room_ids, int(start.timestamp()), duration)
            if sess is None:
                await convo.send_message(f"❌ All {group_name} courts are fully booked at that time.")
                return
            room_id_int = sess.room
            room_id_str = str(room_id_int)
        else:
            sess = Session(int(start.timestamp()), duration, room_id_int)
            if not Schedule(room_id_int).is_available(sess):
                await convo.send_message("❌ That slot is already taken. Please choose a different time.")
                return

        # Show preview with the new session highlighted
        if is_group:
            await send_group_schedule(group_name, to_add=[sess])
        else:
            await send_room_schedule(Schedule(room_id_int), to_add=[sess])

        # Confirm
        sch_item = ScheduleItem.from_session(sess, convo.user_id)
        deadline_warning = (
            f"\n⚠️ Starts in <{Schedule.CANCEL_DEADLINE_MINS} min — non-cancellable after booking."
            if sch_item.past_deadline() else ""
        )
        assigned_line = f"*Assigned room*: _{room_id_str}_\n" if is_group else ""
        msg = wapp_agent.build_interactive(
            header="Schedule Session",
            body=f"{session_str}{assigned_line}\n*Confirm booking?*{deadline_warning}",
            interactive=wapp_agent.create_interactive_buttons(["Yes", "No"])
        )
        reply = await convo.prompt(msg)
        if reply.text != "Yes":
            return

        # Book and sync with session manager
        edit = ScheduleEdit(user, sessions_to_add=[sess])
        edit.apply_all_filters()
        booked = edit.book_sessions()
        if booked:
            for s in booked:
                session_manager.add_session(s)
            court_line = (
                f"*Court type*: {group_name}\n*Assigned room*: {room_id_str}\n"
                if is_group else
                f"*Room*: {room_id_str}\n"
            )
            await convo.send_message(
                f"✅ *Session Booked!*\n"
                f"{court_line}"
                f"*Time*: {sess.start.format('%a, %b %d %H:%M')}\n"
                f"*Duration*: {duration} min\n"
                f"*Cost*: ${cost}\n"
                f"*Balance*: ${user.credits}"
            )
        else:
            await convo.send_message("❌ Booking failed — slot may have just been taken or insufficient credits.")

    async def user_cancel_session():
        """User: cancel a booked session and receive a refund."""
        session_items = Schedule.get_user_schedule(convo.user_id)
        session_items = [si for si in session_items if not si.past_deadline()]
        session_items = session_items[:9]

        if not session_items:
            await convo.send_message(
                f"You have no sessions available for cancellation.\n"
                f"_(Deadline: {Schedule.CANCEL_DEADLINE_MINS} min before start)_"
            )
            return

        session_strs = [
            si.session.start.format("%a, %b %d %H:%M") + f" ({si.session.span}m)"
            for si in session_items
        ]
        selected_str = await prompt_or_auto_select(
            "Cancel Session",
            (
                f"*Your upcoming sessions*\n"
                f"Deadline: {Schedule.CANCEL_DEADLINE_MINS} min before start\n\n"
                f"*Select a session to cancel*"
            ),
            session_strs + ["Go back"],
            cancel_label="Go back"
        )
        if selected_str == "Go back" or selected_str not in session_strs:
            return

        si = session_items[session_strs.index(selected_str)]
        sess = si.session
        room_id_int = sess.room

        # Show schedule with the session to cancel highlighted
        cancel_group = get_room_group(room_id_int)
        if cancel_group:
            await send_group_schedule(cancel_group, to_cancel=[sess])
        else:
            await send_room_schedule(Schedule(room_id_int), to_cancel=[sess])

        room_name = cancel_group or Schedule.ROOMS.get(room_id_int, str(room_id_int))
        refund = ScheduleEdit.get_session_cost(sess)
        msg = wapp_agent.build_interactive(
            header="Cancel Session",
            body=(
                f"*Session info*:\n"
                f"*Room*: _{room_name}_\n"
                f"*Time*: _{sess.start.format('%a, %b %d %H:%M')}_\n"
                f"*Duration*: _{sess.span} min_\n"
                f"*Refund*: _${refund}_\n\n"
                f"*Confirm cancellation?*"
            ),
            interactive=wapp_agent.create_interactive_buttons(["Yes", "No"])
        )
        reply = await convo.prompt(msg)
        if reply.text != "Yes":
            return

        if si.past_deadline():
            await convo.send_message("❌ Cancellation deadline has just passed.")
            return

        edit = ScheduleEdit(user, sessions_to_cancel=[sess])
        cancelled = edit.cancel_sessions()
        if cancelled:
            session_manager.remove_session(sess)
            await convo.send_message(
                f"✅ *Session Cancelled*\n"
                f"*Refund*: ${edit.cancellation_refund}\n"
                f"*New balance*: ${user.credits}"
            )
        else:
            await convo.send_message("❌ Cancellation failed. Please try again.")

    async def user_view_schedule():
        """User: view the schedule image for a court group."""
        update_room_registry()
        group_names = get_group_names()
        choices = group_names
        if not choices:
            await convo.send_message("⚠️ No rooms available yet.")
            return

        selected = await prompt_or_auto_select(
            "View Schedule",
            "*Select a court type*",
            choices + ["Cancel"]
        )
        if selected == "Cancel" or selected not in choices:
            return
        await send_group_schedule(selected)

    async def user_instant_session():
        """User: book a session starting right now in the first available room."""
        update_room_registry()
        group_names = get_group_names()
        if not group_names:
            await convo.send_message("⚠️ No rooms available yet. Please wait...")
            return

        group_name = await prompt_or_auto_select(
            "Instant Session",
            "*Select a court type*",
            group_names + ["Cancel"]
        )
        if group_name == "Cancel" or group_name not in group_names:
            return

        group_room_ids = get_group_rooms(group_name)
        now_ts = int(datetime.now().replace(second=0, microsecond=0).timestamp())
        max_duration = Schedule.max_instant_duration(group_room_ids, now_ts, max_minutes=120)

        all_durations = list(range(15, 121, 15))
        valid_durations = [d for d in all_durations if d <= max_duration]

        if not valid_durations:
            await convo.send_message(f"❌ All {group_name} courts are fully booked right now.")
            return

        duration_texts = [
            (f"{d // 60}h {d % 60:02d}m" if d >= 60 else f"{d}m") + f" (${d * COST_PER_MINUTE})"
            for d in valid_durations
        ]
        selected_dur = await prompt_or_auto_select(
            "Instant Session",
            f"*Court type*: _{group_name}_\n\n*Select duration*",
            duration_texts + ["Cancel"]
        )
        if selected_dur == "Cancel" or selected_dur not in duration_texts:
            return
        duration = valid_durations[duration_texts.index(selected_dur)]
        cost = duration * COST_PER_MINUTE

        if user.credits < cost:
            await convo.send_message(
                f"❌ Insufficient credits\n"
                f"*Required*: ${cost}\n"
                f"*Your balance*: ${user.credits}"
            )
            return

        # Re-read now in case time passed during selection
        now_ts = int(datetime.now().replace(second=0, microsecond=0).timestamp())
        sess = Schedule.find_available_room(group_room_ids, now_ts, duration)
        if sess is None:
            await convo.send_message(f"❌ No {group_name} courts available right now.")
            return

        room_id_str = str(sess.room)
        await send_group_schedule(group_name, to_add=[sess])

        msg = wapp_agent.build_interactive(
            header="Instant Session",
            body=(
                f"*Court type*: _{group_name}_\n"
                f"*Assigned room*: _{room_id_str}_\n"
                f"*Duration*: _{selected_dur}_\n"
                f"*Cost*: _${cost}_\n\n"
                f"*Confirm booking?*\n"
                f"⚠️ Starts immediately — non-cancellable."
            ),
            interactive=wapp_agent.create_interactive_buttons(["Yes", "No"])
        )
        reply = await convo.prompt(msg)
        if reply.text != "Yes":
            return

        edit = ScheduleEdit(user, sessions_to_add=[sess])
        edit.apply_all_filters()
        booked = edit.book_sessions()
        if booked:
            for s in booked:
                session_manager.add_session(s)
            await convo.send_message(
                f"✅ *Instant Session Started!*\n"
                f"*Court type*: {group_name}\n"
                f"*Room*: {room_id_str}\n"
                f"*Duration*: {duration} min\n"
                f"*Ends at*: {sess.end.format('%H:%M')}\n"
                f"*Cost*: ${cost}\n"
                f"*Balance*: ${user.credits}"
            )
        else:
            await convo.send_message("❌ Booking failed — a room was just taken. Please try again.")

    # ===== ADMIN FEATURES =====
    async def control_lights(state):
        """Handle light control for a selected room."""
        room_ids = get_room_ids()
        if not room_ids:
            await convo.send_message("⚠️ No devices discovered yet. Please wait...")
            return
        
        # Prompt for room selection
        msg = wapp_agent.build_interactive(
            header="Control Lights",
            body=f"Select a room to turn {'ON' if state else 'OFF'}",
            interactive=create_menu_options(room_ids + ["Cancel"])
        )
        reply = await convo.prompt(msg)
        
        if reply.text == "Cancel" or reply.text not in room_ids:
            return
        
        # Control the lights
        room_id = reply.text
        result = await facility.control_lights(room_id, state)
        
        if 'error' in result:
            await convo.send_message(f"❌ Error: {result['error']}")
            return
        
        # Send confirmation
        status = "✅ ON" if state else "⭕ OFF"
        await convo.send_message(
            f"*Room {result['room']} lights*: {status}\n"
            f"_Action: {result['action']}_"
        )
    
    async def check_status(room_id):
        """Check the status of a room."""
        result = await facility.get_room_status(room_id)
        
        if 'error' in result:
            await convo.send_message(f"❌ Error: {result['error']}")
            return
        
        # Build status message
        status_lines = [f"*Room {result['room']} Status*"]
        
        if 'light' in result:
            light_icon = "✅" if result['light'] == "on" else "⭕"
            status_lines.append(f"Lights: {light_icon} {result['light'].upper()}")
        
        if 'lock' in result:
            lock_icon = "🔒" if result['lock'] == "locked" else "🔓"
            status_lines.append(f"Lock: {lock_icon} {result['lock'].upper()}")
        
        await convo.send_message("\n".join(status_lines))
    
    async def view_system_status():
        """Display comprehensive system status for all sessions and rooms."""
        # Get all sessions
        all_sessions = session_manager.get_all_sessions()
        active_sessions = session_manager.active_sessions
        
        # Get all rooms
        room_ids = get_room_ids()
        
        # Build status message
        status_lines = ["*🔍 SYSTEM STATUS*\n"]
        
        # === SESSIONS SECTION ===
        status_lines.append("*📅 SESSIONS*")
        if not all_sessions:
            status_lines.append("   No sessions scheduled")
        else:
            # Group by status
            active = [s for s in all_sessions if s in active_sessions]
            not_started = [s for s in all_sessions if not s.has_started()]
            ended = [s for s in all_sessions if s.has_ended()]
            
            if active:
                status_lines.append("   🟢 *Active*")
                for s in active:
                    status_lines.append(f"      Room {s.room}: {s.start.format('%H:%M')} - {s.end.format('%H:%M')}")
            
            if not_started:
                status_lines.append("   🟡 *Scheduled*")
                for s in not_started:
                    status_lines.append(f"      Room {s.room}: {s.start.format('%H:%M')} - {s.end.format('%H:%M')}")
            
            if ended:
                status_lines.append("   🔴 *Ended*")
                for s in ended:
                    status_lines.append(f"      Room {s.room}: {s.start.format('%H:%M')} - {s.end.format('%H:%M')}")
        
        # === ROOMS SECTION ===
        status_lines.append("\n*💡 ROOMS*")
        if not room_ids:
            status_lines.append("   No devices discovered")
        else:
            for room_id in room_ids:
                result = await facility.get_room_status(room_id)
                if 'error' in result:
                    status_lines.append(f"   Room {room_id}: ❌ Error")
                else:
                    parts = [f"Room {room_id}:"]
                    if 'light' in result:
                        light_status = "✅ ON" if result['light'] == "on" else "⭕ OFF"
                        parts.append(f"Lights {light_status}")
                    if 'lock' in result:
                        lock_status = "🔒" if result['lock'] == "locked" else "🔓"
                        parts.append(f"{lock_status}")
                    status_lines.append(f"   {' | '.join(parts)}")
        
        await convo.send_message("\n".join(status_lines))
    
    async def admin_start_session():
        """Admin: Start a timed session that automatically controls lights."""
        room_ids = get_room_ids()
        if not room_ids:
            await convo.send_message("⚠️ No devices discovered yet. Please wait...")
            return
        
        # Prompt for room selection
        msg = wapp_agent.build_interactive(
            header="Start Session",
            body="Select a room",
            interactive=create_menu_options(room_ids + ["Cancel"])
        )
        reply = await convo.prompt(msg)
        
        if reply.text == "Cancel" or reply.text not in room_ids:
            return
        
        room_id = reply.text
        
        # Prompt for duration
        durations = [5, 10, 15, 30, 45, 60, 90, 120]  # minutes
        duration_texts = [f"{d} minutes" for d in durations]
        msg = wapp_agent.build_interactive(
            header="Start Session",
            body=f"*Room*: {room_id}\nSelect session duration",
            interactive=create_menu_options(duration_texts + ["Cancel"])
        )
        reply = await convo.prompt(msg)
        
        if reply.text == "Cancel" or reply.text not in duration_texts:
            return
        
        duration = durations[duration_texts.index(reply.text)]
        
        # Create session starting now
        now = Timestamp.now()
        session = Session(now, span=duration, room=int(room_id))
        
        # Add to session manager (hardware callbacks) and schedule (WhatsApp visibility)
        session_manager.add_session(session)
        Schedule(int(room_id)).add_session(session, 'admin')

        await convo.send_message(
            f"✅ *Session Started*\n"
            f"*Room*: {room_id}\n"
            f"*Duration*: {duration} minutes\n"
            f"*Ends at*: {Timestamp(session.end).format('%H:%M')}\n\n"
            f"💡 Lights ON\n"
            f"🔓 Door UNLOCKED\n"
            f"⏱️ Countdown started"
        )

    # ===== ROOM CONTROL SUBMENU =====
    async def room_control_submenu(room_id):
        """Control submenu for a specific room."""
        while True:
            msg = wapp_agent.build_interactive(
                header=f"Room {room_id} Control",
                body="Select an operation",
                interactive=create_menu_options([
                    "💡 Turn ON lights",
                    "💡 Turn OFF lights",
                    "🔒 Lock",
                    "🔓 Unlock",
                    "🟢 Open Room",
                    "🔴 Close Room",
                    "⏱️ Start Session",
                    "← Back"
                ])
            )
            reply = await convo.prompt(msg)
            
            if reply.text == "← Back":
                return
            elif reply.text == "💡 Turn ON lights":
                result = await facility.control_lights(room_id, True)
                if 'error' in result:
                    await convo.send_message(f"❌ Error: {result['error']}")
                else:
                    await convo.send_message(f"✅ Room {room_id} lights turned ON")
            elif reply.text == "💡 Turn OFF lights":
                result = await facility.control_lights(room_id, False)
                if 'error' in result:
                    await convo.send_message(f"❌ Error: {result['error']}")
                else:
                    await convo.send_message(f"⭕ Room {room_id} lights turned OFF")
            elif reply.text == "🔒 Lock":
                result = await facility.control_lock(room_id, True)
                if 'error' in result:
                    await convo.send_message(f"❌ Error: {result['error']}")
                else:
                    await convo.send_message(f"🔒 Room {room_id} LOCKED")
            elif reply.text == "🔓 Unlock":
                result = await facility.control_lock(room_id, False)
                if 'error' in result:
                    await convo.send_message(f"❌ Error: {result['error']}")
                else:
                    await convo.send_message(f"🔓 Room {room_id} UNLOCKED")
            elif reply.text == "🟢 Open Room":
                # Execute both operations
                light_result = await facility.control_lights(room_id, True)
                lock_result = await facility.control_lock(room_id, False)
                
                if 'error' in light_result or 'error' in lock_result:
                    await convo.send_message(f"⚠️ Room {room_id} partially opened (check errors)")
                else:
                    await convo.send_message(f"🟢 Room {room_id} OPENED\n💡 Lights ON\n🔓 Unlocked")
            elif reply.text == "🔴 Close Room":
                # Execute both operations
                light_result = await facility.control_lights(room_id, False)
                lock_result = await facility.control_lock(room_id, True)
                
                if 'error' in light_result or 'error' in lock_result:
                    await convo.send_message(f"⚠️ Room {room_id} partially closed (check errors)")
                else:
                    await convo.send_message(f"🔴 Room {room_id} CLOSED\n💡 Lights OFF\n🔒 Locked")
            elif reply.text == "⏱️ Start Session":
                # Prompt for duration
                durations = [5, 10, 15, 30, 45, 60, 90, 120]  # minutes
                duration_texts = [f"{d} minutes" for d in durations]
                msg = wapp_agent.build_interactive(
                    header="Start Session",
                    body=f"*Room*: {room_id}\nSelect session duration",
                    interactive=create_menu_options(duration_texts + ["Cancel"])
                )
                duration_reply = await convo.prompt(msg)
                
                if duration_reply.text == "Cancel" or duration_reply.text not in duration_texts:
                    continue
                
                duration = durations[duration_texts.index(duration_reply.text)]
                
                # Create session starting now
                now = Timestamp.now()
                session = Session(now, span=duration, room=int(room_id))
                
                # Add to session manager (hardware callbacks) and schedule (WhatsApp visibility)
                session_manager.add_session(session)
                Schedule(int(room_id)).add_session(session, 'admin')

                await convo.send_message(
                    f"✅ *Session Started*\n"
                    f"*Room*: {room_id}\n"
                    f"*Duration*: {duration} minutes\n"
                    f"*Ends at*: {Timestamp(session.end).format('%H:%M')}\n\n"
                    f"💡 Lights ON\n"
                    f"🔓 Door UNLOCKED\n"
                    f"⏱️ Countdown started"
                )

    # ===== ADMIN SUBMENU =====
    async def admin_add_credits():
        """Admin: add or deduct credits for any user."""
        msg = wapp_agent.build_interactive(
            header="Add Credits",
            body="Enter the *user phone number* (e.g. 1234567890)",
            interactive=wapp_agent.create_interactive_buttons(["Cancel"])
        )
        reply = await convo.prompt(msg)
        if reply.text == "Cancel":
            return
        target_id = reply.text.strip()

        msg = wapp_agent.build_interactive(
            header="Add Credits",
            body=f"User: _{target_id}_\nEnter the *amount* to add (negative to deduct)",
            interactive=wapp_agent.create_interactive_buttons(["Cancel"])
        )
        reply = await convo.prompt(msg)
        if reply.text == "Cancel":
            return
        try:
            amount = int(reply.text)
        except ValueError:
            await convo.send_message("❌ Invalid amount — please enter a whole number.")
            return

        target_user = User(target_id)
        target_user.credits += amount
        await convo.send_message(
            f"✅ {'Added' if amount >= 0 else 'Deducted'} {abs(amount)} credits "
            f"{'to' if amount >= 0 else 'from'} _{target_id}_\n"
            f"*New balance*: ${target_user.credits}"
        )
    async def admin_submenu():
        """Admin panel with privileged operations."""
        while True:
            # Get available rooms
            room_ids = get_room_ids()
            
            # Build menu with System Status + All Lights + individual rooms
            menu_options = ["🔍 System Status", "💰 Add Credits"]
            if room_ids:
                menu_options.extend(["💡 All Lights ON", "💡 All Lights OFF", "⏱️ Start Session"])
                menu_options.extend([f"Room {room_id}" for room_id in room_ids])
            menu_options.append("← Back to Main Menu")
            
            msg = wapp_agent.build_interactive(
                header="Admin Panel",
                body="*Administrator Operations*\nSelect an option",
                interactive=create_menu_options(menu_options)
            )
            reply = await convo.prompt(msg)
            
            if reply.text == "← Back to Main Menu":
                return
            elif reply.text == "🔍 System Status":
                await view_system_status()
            elif reply.text == "💰 Add Credits":
                await admin_add_credits()
            elif reply.text == "💡 All Lights ON":
                # Turn on lights in all rooms
                results = []
                for room_id in room_ids:
                    result = await facility.control_lights(room_id, True)
                    if 'error' in result:
                        results.append(f"Room {room_id}: ❌ Error")
                    else:
                        results.append(f"Room {room_id}: ✅ ON")
                await convo.send_message("*All Lights Control*\n" + "\n".join(results))
            elif reply.text == "💡 All Lights OFF":
                # Turn off lights in all rooms
                results = []
                for room_id in room_ids:
                    result = await facility.control_lights(room_id, False)
                    if 'error' in result:
                        results.append(f"Room {room_id}: ❌ Error")
                    else:
                        results.append(f"Room {room_id}: ⭕ OFF")
                await convo.send_message("*All Lights Control*\n" + "\n".join(results))
            elif reply.text == "⏱️ Start Session":
                await admin_start_session()
            else:
                # Check if it's a room selection
                for room_id in room_ids:
                    if reply.text == f"Room {room_id}":
                        await room_control_submenu(room_id)
                        break
    
    # ===== MAIN MENU =====
    async def main_menu():
        """Main menu with user and admin options."""
        while True:
            msg = wapp_agent.build_interactive(
                header="Court Access Control",
                body=f"*Balance*: _${user.credits}_\n*Welcome!*\nWhat would you like to do?",
                interactive=create_menu_options([
                    "📆 Schedule Session",
                    "⚡ Instant Session",
                    "❌ Cancel Session",
                    "📅 View Schedule",
                    "🔧 Admin Panel"
                ])
            )
            reply = await convo.prompt(msg)
            
            if reply.text == "📆 Schedule Session":
                await user_schedule_session()
            elif reply.text == "⚡ Instant Session":
                await user_instant_session()
            elif reply.text == "❌ Cancel Session":
                await user_cancel_session()
            elif reply.text == "📅 View Schedule":
                await user_view_schedule()
            elif reply.text == "🔧 Admin Panel":
                await admin_submenu()
    
    # Start the conversation
    try:
        await main_menu()
    except Exception as e:
        traceback.print_exc()
        print(e)

# Main startup
async def main():
    """Main entry point - start discovery, session manager, and agent."""
    print("Starting facility manager with device discovery...")
    facility.start_discovery()
    
    # Get the event loop for session callbacks
    loop = asyncio.get_running_loop()
    
    # Set up session manager callbacks to control lights, locks, and countdown
    def on_session_start(session):
        print(f"[SessionManager] Starting session for room {session.room}")
        
        # Turn on lights
        future = asyncio.run_coroutine_threadsafe(
            facility.control_lights(str(session.room), True),
            loop
        )
        try:
            result = future.result(timeout=5)
            print(f"[SessionManager] Lights ON for room {session.room}: {result}")
        except Exception as e:
            print(f"[SessionManager] Error turning lights ON: {e}")
        
        # Unlock door
        future = asyncio.run_coroutine_threadsafe(
            facility.control_lock(str(session.room), False),
            loop
        )
        try:
            result = future.result(timeout=5)
            print(f"[SessionManager] Door UNLOCKED for room {session.room}: {result}")
        except Exception as e:
            print(f"[SessionManager] Error unlocking door: {e}")
        
        # Start countdown (span is in minutes, convert to seconds)
        # Use Timestamp.MIN to account for test mode
        countdown_seconds = session.span * Timestamp.MIN
        future = asyncio.run_coroutine_threadsafe(
            facility.set_countdown(str(session.room), countdown_seconds),
            loop
        )
        try:
            result = future.result(timeout=5)
            print(f"[SessionManager] Countdown set for room {session.room}: {countdown_seconds}s")
        except Exception as e:
            print(f"[SessionManager] Error setting countdown: {e}")

    def on_session_end(session):
        print(f"[SessionManager] Ending session for room {session.room}")
        
        # Turn off lights
        future = asyncio.run_coroutine_threadsafe(
            facility.control_lights(str(session.room), False),
            loop
        )
        try:
            result = future.result(timeout=5)
            print(f"[SessionManager] Lights OFF for room {session.room}: {result}")
        except Exception as e:
            print(f"[SessionManager] Error turning lights OFF: {e}")
        
        # Lock door
        future = asyncio.run_coroutine_threadsafe(
            facility.control_lock(str(session.room), True),
            loop
        )
        try:
            result = future.result(timeout=5)
            print(f"[SessionManager] Door LOCKED for room {session.room}: {result}")
        except Exception as e:
            print(f"[SessionManager] Error locking door: {e}")
        
        # Reset countdown to 0
        future = asyncio.run_coroutine_threadsafe(
            facility.set_countdown(str(session.room), 0),
            loop
        )
        try:
            result = future.result(timeout=5)
            print(f"[SessionManager] Countdown reset for room {session.room}")
        except Exception as e:
            print(f"[SessionManager] Error resetting countdown: {e}")

    session_manager.start_session = on_session_start
    session_manager.end_session = on_session_end
    
    print("Starting session manager...")
    session_manager.start()
    
    print("Starting WhatsApp agent...")
    await agent.start(handle_conversation)

# Start the agent and handle conversations
asyncio.run(main())
