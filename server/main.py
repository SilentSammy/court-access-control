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
        light_endpoints = [e for e in endpoints if e.endswith('/lights')]
        return [e.split('/')[0] for e in light_endpoints]
    
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
    
    async def check_status():
        """Check the status of a selected room."""
        room_ids = get_room_ids()
        if not room_ids:
            await convo.send_message("⚠️ No devices discovered yet. Please wait...")
            return
        
        # Prompt for room selection
        msg = wapp_agent.build_interactive(
            header="Room Status",
            body="Select a room to check status",
            interactive=create_menu_options(room_ids + ["Cancel"])
        )
        reply = await convo.prompt(msg)
        
        if reply.text == "Cancel" or reply.text not in room_ids:
            return
        
        # Get room status
        room_id = reply.text
        result = await facility.get_room_status(room_id)
        
        if 'error' in result:
            await convo.send_message(f"❌ Error: {result['error']}")
            return
        
        # Send status
        light_icon = "✅" if result['light'] == "on" else "⭕"
        await convo.send_message(
            f"*Room {result['room']} Status*\n"
            f"Lights: {light_icon} {result['light'].upper()}"
        )
    
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
            f"Lights will turn ON when session starts and OFF when it ends."
        )
    
    # ===== LIGHT CONTROL SUBMENU =====
    async def lights_submenu():
        """Submenu for light control operations."""
        while True:
            msg = wapp_agent.build_interactive(
                header="Control Lights",
                body="Select an operation",
                interactive=create_menu_options([
                    "Turn ON lights",
                    "Turn OFF lights",
                    "Check room status",
                    "← Back"
                ])
            )
            reply = await convo.prompt(msg)
            
            if reply.text == "← Back":
                return
            elif reply.text == "Turn ON lights":
                await control_lights(True)
            elif reply.text == "Turn OFF lights":
                await control_lights(False)
            elif reply.text == "Check room status":
                await check_status()
    
    # ===== ADMIN SUBMENU =====
    async def admin_submenu():
        """Admin panel with privileged operations."""
        while True:
            msg = wapp_agent.build_interactive(
                header="Admin Panel",
                body="*Administrator Operations*\nSelect an option",
                interactive=create_menu_options([
                    "💡 Control Lights",
                    "⏱️ Start Session",
                    "← Back to Main Menu"
                ])
            )
            reply = await convo.prompt(msg)
            
            if reply.text == "← Back to Main Menu":
                return
            elif reply.text == "💡 Control Lights":
                await lights_submenu()
            elif reply.text == "⏱️ Start Session":
                await admin_start_session()
    
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
    
    # Set up session manager callbacks to control lights
    def on_session_start(session):
        print(f"[SessionManager] Starting session for room {session.room}")
        future = asyncio.run_coroutine_threadsafe(
            facility.control_lights(str(session.room), True),
            loop
        )
        try:
            result = future.result(timeout=5)
            print(f"[SessionManager] Lights ON for room {session.room}: {result}")
        except Exception as e:
            print(f"[SessionManager] Error turning lights ON: {e}")

    def on_session_end(session):
        print(f"[SessionManager] Ending session for room {session.room}")
        future = asyncio.run_coroutine_threadsafe(
            facility.control_lights(str(session.room), False),
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

# Start the agent and handle conversations
asyncio.run(main())
