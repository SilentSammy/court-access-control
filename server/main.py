import os
import traceback
import wapp_agent as wapp_agent
from wapp_agent import WAppAgent, Convo
import asyncio
from facility import FacilityManager
from device_discoverer import DeviceDiscoverer
from session_manager import SessionManager
from session import Session, Timestamp

# SETUP
facility = FacilityManager(discoverer=DeviceDiscoverer(
    discovery_interval=300,
    health_check_interval=5,
    scan_networks=[
        "192.168.137.0/24",  # Windows hotspot
        "192.168.1.0/24"     # Home network (UPDATE: check ipconfig at home for your actual network)
    ]
))
session_manager = SessionManager(check_interval=5, sessions_file="sessions.txt")
agent = WAppAgent(config_file=os.path.dirname(os.path.abspath(__file__))+'\\wapp.json')
Timestamp.enable_test_mode()  # Enable test mode for faster session testing



async def handle_conversation(convo: Convo):
    def get_room_ids():
        """Get available room IDs from discovered endpoints."""
        endpoints = facility.discoverer.get_all_endpoints()
        # Extract unique room IDs from endpoints like "1/lights", "1/lock", etc.
        room_ids = set()
        for e in endpoints:
            if e.endswith('/lights') or e.endswith('/lock'):
                room_id = e.split('/')[0]
                room_ids.add(room_id)
        return sorted(room_ids)
    
    def create_menu_options(options):
        """Helper to create interactive list."""
        return wapp_agent.create_interactive_list("Select", options)
    
    # ===== USER FEATURES (Placeholders for future implementation) =====
    async def user_schedule_session():
        """Placeholder for user session scheduling."""
        await convo.send_message("🚧 *Coming Soon*\nSession scheduling feature is under development")
    
    async def user_cancel_session():
        """Placeholder for user session cancellation."""
        await convo.send_message("🚧 *Coming Soon*\nSession cancellation feature is under development")
    
    async def user_view_schedule():
        """Placeholder for schedule viewing."""
        await convo.send_message("🚧 *Coming Soon*\nSchedule viewing feature is under development")
    
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
        
        # Add to session manager
        session_manager.add_session(session)
        
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
                
                # Add to session manager
                session_manager.add_session(session)
                
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
    async def admin_submenu():
        """Admin panel with privileged operations."""
        while True:
            # Get available rooms
            room_ids = get_room_ids()
            
            # Build menu with System Status + individual rooms
            menu_options = ["🔍 System Status"]
            if room_ids:
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
                body="*Welcome!*\nWhat would you like to do?",
                interactive=create_menu_options([
                    "📆 Schedule Session",
                    "❌ Cancel Session",
                    "📅 View Schedule",
                    "🔧 Admin Panel"
                ])
            )
            reply = await convo.prompt(msg)
            
            if reply.text == "📆 Schedule Session":
                await user_schedule_session()
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
