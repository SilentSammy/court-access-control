import os
from wapp.wapp_agent import WAppAgent, build_interactive, create_interactive_list, create_interactive_buttons, Convo
import asyncio

# Business logic imports
from server.facility import FacilityManager, DeviceDiscoverer
from server.user import User
from schedule_config import global_schedule, squash_schedule, schedules
from server.schedule import ScheduleDisplayer
from server.smart_scheduler import SmartScheduler
from server.schedule_edit import ScheduleEdit
from server.session_manager import SessionManager
from wapp.wapp_agent import build_media

agent = WAppAgent(config_file=os.path.dirname(os.path.abspath(__file__))+'\\wapp.json')
manager = FacilityManager(discoverer=DeviceDiscoverer(
    discovery_interval=10,
    health_check_interval=5,
    check_localhost=True,
    scan_networks=[
        "192.168.137.0/24",  # Windows hotspot
        "192.168.1.0/24"     # Home network
    ],
    # exclude_ips=["192.168.1.226"]  # Exclude problematic IPs
))
session_manager = SessionManager(check_interval=5, sessions_file="sessions.txt")
ADMIN_USER_IDS = ['50766180742', '5218114142626']  # Hardcoded admin user IDs

# --- ADMIN OPTIONS ---
async def show_system_status(convo: Convo):
    """Display all rooms and their current status."""
    try:
        # Get all rooms
        rooms = manager.get_room_ids()
        
        if not rooms:
            await convo.send_message("❌ No rooms available")
            return
        
        # Get status for each room
        status_lines = ["*📊 System Status*\n"]
        for room_id in rooms:
            try:
                status = await manager.get_room_status(room_id=room_id)
                if "error" not in status:
                    light_emoji = "💡" if status.get("light") == "on" else "🌙"
                    status_lines.append(f"{light_emoji} Room {room_id}: {status.get('light', 'unknown').upper()}")
                else:
                    status_lines.append(f"❌ Room {room_id}: {status['error']}")
            except Exception as e:
                status_lines.append(f"❌ Room {room_id}: Error")
        
        await convo.send_message("\n".join(status_lines))
    except Exception as e:
        await convo.send_message(f"❌ Error getting status: {str(e)}")

async def show_room_selection(convo: Convo, state: int) -> str:
    """Display room selection menu and return chosen room."""
    try:
        action = "on" if state == 1 else "off"
        rooms = manager.get_room_ids()
        room_choices = { f"Room {r}": r for r in rooms }
        
        if not rooms:
            await convo.send_message("❌ No rooms available")
            return None
        
        msg = build_interactive(
            header=f"Turn {action} Light",
            body="*Select a room:*",
            interactive=create_interactive_list(
                "Select",
                list(room_choices.keys()),
            )
        )
        room_choice = (await convo.prompt(msg)).text
        if room_choice:
            await control_single_light(convo, room_id=room_choices[room_choice], state=state)
    except Exception as e:
        await convo.send_message(f"❌ Error loading rooms: {str(e)}")
        return None

async def control_single_light(convo: Convo, room_id: str, state: int):
    """Control a single room's light."""
    try:
        action = "on" if state == 1 else "off"
        result = await manager.control_lights(room_id=room_id, state=state)
        if "error" not in result:
            light_status = result.get("light", "unknown").upper()
            emoji = "💡" if light_status == "ON" else "🌙"
            await convo.send_message(f"{emoji} Room {room_id} light turned {action}")
        else:
            await convo.send_message(f"❌ Error: {result['error']}")
    except Exception as e:
        await convo.send_message(f"❌ Error controlling light: {str(e)}")

async def control_all_lights(convo: Convo, state: int, action: str):
    """Control all room lights."""
    try:
        await convo.send_message(f"⏳ Turning {action} all lights...")
        rooms = manager.get_room_ids()
        results = []
        for room_id in rooms:
            result = await manager.control_lights(room_id, state)
            results.append(result)
        emoji = "✨" if state == 1 else "⚫"
        await convo.send_message(f"{emoji} All {len(results)} room(s) turned {action}")
    except Exception as e:
        await convo.send_message(f"❌ Error controlling lights: {str(e)}")

async def show_schedule(convo: Convo, user: User):
    """Display the schedule as an image and list user's sessions."""
    try:
        await convo.send_message("⏳ Generating schedule...")
        
        # Get and display user's sessions textually
        user_sessions = sorted(user.sessions, key=lambda s: s.start)
        
        if user_sessions:
            session_lines = ["*📅 Your Booked Sessions:*\n"]
            
            for session in user_sessions:
                # Find the schedule and room name for this session
                room_name = f"Room {session.room}"
                for schedule in schedules:
                    if session.room in schedule.room_ids:
                        room_name = schedule.name_map.get(session.room, f"Room {session.room}")
                        break
                
                # Format the session info
                start_str = session.start.format("%a %b %d, %I:%M %p")
                end_str = session.end.format("%I:%M %p")
                duration_hrs = session.span / 60
                
                # Status indicator
                if session.has_ended():
                    status = "✓ Completed"
                elif session.has_started():
                    status = "🟢 Ongoing"
                else:
                    status = "📅 Upcoming"
                
                session_lines.append(
                    f"{status}\n"
                    f"  *{room_name}*\n"
                    f"  {start_str} - {end_str}\n"
                    f"  Duration: {duration_hrs:.1f}h\n"
                )
            
            await convo.send_message("\n".join(session_lines))
        else:
            await convo.send_message("*📅 Your Booked Sessions:*\n\nNo sessions booked.")
        
        # Create displayer and generate image
        displayer = ScheduleDisplayer(squash_schedule)
        displayer.user_id = user.id  # Highlight user's sessions
        image_path = displayer.display()
        
        # Upload and send the image
        media_id = await convo.agent.upload_media(image_path)
        await convo.send_message(build_media(media_id))
        
    except Exception as e:
        await convo.send_message(f"❌ Error displaying schedule: {str(e)}")

async def manage_sessions(convo: Convo, user: User):
    """Manage user sessions - book or cancel sessions."""
    try:
        # Show the schedule first
        await show_schedule(convo, user)
        
        # Prompt for natural language input
        await convo.send_message("💬 Tell me what you'd like to do (e.g., 'book Squash tomorrow at 3pm for 1h' or 'cancel my Saturday sessions'):")
        response = await convo.wait_for_message()
        user_input = response.text.strip()
        
        await convo.send_message("⏳ Processing your request...")
        
        # Parse natural language using SmartScheduler
        scheduler = SmartScheduler(user, schedules)
        raw_response = scheduler.process_user_message(user_input)
        session_dicts = scheduler.parse_response(raw_response)
        
        if not session_dicts:
            await convo.send_message("❌ Could not understand your request. Please try again.")
            return
        
        # Convert to session objects
        sessions_to_add, sessions_to_cancel = scheduler.segregate_sessions(session_dicts)
        sessions_to_add = scheduler.try_get_sessions(sessions_to_add)
        sessions_to_cancel = scheduler.try_get_sessions(sessions_to_cancel)
        
        if not sessions_to_add and not sessions_to_cancel:
            await convo.send_message("❌ No valid sessions found. Please check your request.")
            return
        
        # Create schedule edit and apply filters
        edit = ScheduleEdit(user, global_schedule, sessions_to_add, sessions_to_cancel)
        edit.apply_all_filters()
        
        if not edit.sessions_to_add and not edit.sessions_to_cancel:
            await convo.send_message("❌ No valid sessions after filtering (conflicts, affordability, etc.)")
            return
        
        # Show single unified preview with all changes
        await convo.send_message(f"📊 Preview: {len(edit.sessions_to_add)} to add, {len(edit.sessions_to_cancel)} to cancel")
        
        # Determine which schedules are affected
        affected_room_ids = set()
        for session in edit.all_sessions:
            affected_room_ids.add(session.room)
        
        # Get all schedules that contain affected rooms
        affected_schedules = []
        for schedule in schedules:
            if any(room_id in schedule.room_ids for room_id in affected_room_ids):
                affected_schedules.append(schedule)
        
        # If no affected schedules found, fall back to all schedules
        if not affected_schedules:
            affected_schedules = schedules
        
        # Create a single displayer with all affected schedules
        displayer = ScheduleDisplayer(affected_schedules)
        displayer.user_id = user.id
        displayer.sessions_to_add = edit.sessions_to_add
        displayer.sessions_to_cancel = edit.sessions_to_cancel
        preview_path = displayer.display()
        
        # Upload and send the unified preview
        media_id = await convo.agent.upload_media(preview_path)
        await convo.send_message(build_media(media_id))
        
        # Show cost summary
        cost_msg = (
            f"💰 *Cost Summary:*\n"
            f"  • To add: {edit.cost_to_add} credits\n"
            f"  • Refund: {edit.cancellation_refund} credits\n"
            f"  • Net cost: {edit.net_cost} credits\n"
            f"  • Current balance: {user.credits} credits\n"
            f"  • New balance: {user.credits - edit.net_cost} credits"
        )
        await convo.send_message(cost_msg)
        
        # Prompt for confirmation
        confirm_msg = build_interactive(
            body="Confirm these changes?",
            interactive=create_interactive_buttons(["✅ Confirm", "❌ Cancel"])
        )
        confirmation = await convo.prompt(confirm_msg)
        
        if "confirm" in confirmation.text.lower():
            # Apply changes
            cancelled = edit.cancel_sessions()
            booked = edit.book_sessions()
            
            # Sync with hardware control queue
            for sess in booked:
                session_manager.add_session(sess)
            for sess in cancelled:
                session_manager.remove_session(sess)
            
            result_msg = (
                f"✅ *Changes applied!*\n"
                f"  • Booked: {len(booked)} session(s)\n"
                f"  • Cancelled: {len(cancelled)} session(s)\n"
                f"  • New balance: {user.credits} credits"
            )
            await convo.send_message(result_msg)
            
            # Show updated schedule
            await show_schedule(convo, user)
        else:
            await convo.send_message("❌ Changes cancelled. No modifications were made.")
        
    except Exception as e:
        await convo.send_message(f"❌ Error managing sessions: {str(e)}")

async def update_user_balance(convo: Convo, current_user: User):
    """Update balance for self or another user."""
    try:
        # Ask for user ID with "Me" button
        msg = build_interactive(
            body="Select yourself or type another user ID:",
            interactive=create_interactive_buttons(["Me"])
        )
        response = await convo.prompt(msg)
        target_user_id = response.text.strip()
        
        if target_user_id.lower() == "me":
            target_user_id = current_user.id
        
        # Ask for new balance
        await convo.send_message(f"Enter new balance for user `{target_user_id}`:\n(Use +/- to add/subtract, or enter absolute value)")
        response2 = await convo.wait_for_message()
        
        balance_input = response2.text.strip()
        target_user = User(target_user_id, global_schedule)
        
        try:
            # Check if it's a relative change (+ or -)
            if balance_input.startswith('+') or balance_input.startswith('-'):
                change = int(balance_input)
                old_balance = target_user.credits
                new_balance = old_balance + change
                target_user.credits = new_balance
                await convo.send_message(f"✅ Balance updated!\nUser: {target_user_id}\nOld Balance: {old_balance} credits\nChange: {change:+d} credits\nNew Balance: {new_balance} credits")
            else:
                # Absolute value
                new_balance = int(balance_input)
                target_user.credits = new_balance
                await convo.send_message(f"✅ Balance updated!\nUser: {target_user_id}\nNew Balance: {new_balance} credits")
        except ValueError:
            await convo.send_message("❌ Invalid balance amount. Must be a number.")
            return
        
    except Exception as e:
        await convo.send_message(f"❌ Error updating balance: {str(e)}")

async def show_main_menu(convo: Convo, user: User) -> str:
    """Display main menu and return user's choice."""
    # Admin-only options
    admin_actions = {
        "📊 System Status": lambda: show_system_status(convo),
        "💡 Turn on light": lambda: show_room_selection(convo, 1),
        "🌙 Turn off light": lambda: show_room_selection(convo, 0),
        "✨ Turn on all": lambda: control_all_lights(convo, state=1, action="on"),
        "⚫ Turn off all": lambda: control_all_lights(convo, state=0, action="off"),
        "💰 Update Balance": lambda: update_user_balance(convo, user),
    }

    # User options (available to all)
    user_actions = {
        "📅 View Schedule": lambda: show_schedule(convo, user),
        "🏟️ Book or cancel a session": lambda: manage_sessions(convo, user),
    }

    # Build menu based on user privileges
    is_admin = user.id in ADMIN_USER_IDS
    menu_actions = {**admin_actions, **user_actions} if is_admin else user_actions

    # Count user's sessions
    user_sessions = user.sessions
    ongoing = sum(1 for s in user_sessions if s.has_started() and not s.has_ended())
    upcoming = sum(1 for s in user_sessions if not s.has_started())
    
    msg = build_interactive(
        header="Facility Control",
        body=(
            f"*Balance: {user.credits} credits*\n"
            f"*Sessions: {ongoing} ongoing • {upcoming} upcoming*\n\n"
            f"What would you like to do?"
        ),
        interactive=create_interactive_list("Select", list(menu_actions.keys()))
    )
    choice = (await convo.prompt(msg)).text
    
    # Execute the selected action
    action = menu_actions.get(choice)
    if action:
        await action()

async def handle_conversation(convo: Convo):
    try:
        first_msg = await convo.wait_for_message() # Discard first message
        user_id = convo.user_id
        
        # Create User instance with global schedule
        user = User(user_id, global_schedule)

        while True:
            await show_main_menu(convo, user)

    except Exception as e:
        print(f"Error in conversation: {e}")

async def main():
    """Main entry point - start discovery, session manager, and agent."""
    print("Starting facility manager with device discovery...")
    manager.start_discovery()
    
    # Get the event loop for session callbacks
    loop = asyncio.get_running_loop()
    
    # Set up session manager callbacks to control lights
    def on_session_start(session):
        print(f"[SessionManager] Starting session for room {session.room}")
        
        # Turn on lights (schedule coroutine from thread)
        future = asyncio.run_coroutine_threadsafe(
            manager.control_lights(str(session.room), 1),
            loop
        )
        try:
            result = future.result(timeout=5)
            print(f"[SessionManager] Lights ON for room {session.room}: {result}")
        except Exception as e:
            print(f"[SessionManager] Error turning lights ON: {e}")
    
    def on_session_end(session):
        print(f"[SessionManager] Ending session for room {session.room}")
        
        # Turn off lights (schedule coroutine from thread)
        future = asyncio.run_coroutine_threadsafe(
            manager.control_lights(str(session.room), 0),
            loop
        )
        try:
            result = future.result(timeout=5)
            print(f"[SessionManager] Lights OFF for room {session.room}: {result}")
        except Exception as e:
            print(f"[SessionManager] Error turning lights OFF: {e}")
    
    session_manager.start_session = on_session_start
    session_manager.end_session = on_session_end
    
    print("Starting session manager...")
    session_manager.start()
    
    print("Starting WhatsApp agent...")
    await agent.start(handle_conversation)

asyncio.run(main())

