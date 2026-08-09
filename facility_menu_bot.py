import os
from wapp.wapp_agent import WAppAgent, build_interactive, create_interactive_list, create_interactive_buttons, Convo
import asyncio

# Business logic imports
from server.facility import FacilityManager, DeviceDiscoverer

agent = WAppAgent(config_file=os.path.dirname(os.path.abspath(__file__))+'\\wapp.json')
manager = FacilityManager(discoverer=DeviceDiscoverer(
    discovery_interval=10,
    health_check_interval=5,
    check_localhost=True,
    scan_networks=[
        "192.168.137.0/24",  # Windows hotspot
        "192.168.1.0/24"     # Home network
    ]
))

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

async def show_main_menu(convo: Convo) -> str:
    """Display main menu and return user's choice."""
    choices = [
            "📊 System Status",
            "💡 Turn on light",
            "🌙 Turn off light",
            "✨ Turn on all",
            "⚫ Turn off all"
    ]
    msg = build_interactive(
        header="Facility Control",
        body="*What would you like to do?*",
        interactive=create_interactive_list( "Select", choices )
    )
    choice = (await convo.prompt(msg)).text
    
    if choice == choices[0]:
        await show_system_status(convo)
    
    elif choice == choices[1]:
        # Turn on single light
        await show_room_selection(convo, 1)
    
    elif choice == choices[2]:
        # Turn off single light
        await show_room_selection(convo, 0)
    
    elif choice == choices[3]:
        # Turn on all lights
        await control_all_lights(convo, state=1, action="on")
    
    elif choice == choices[4]:
        # Turn off all lights
        await control_all_lights(convo, state=0, action="off")

async def handle_conversation(convo: Convo):
    try:
        first_msg = await convo.wait_for_message()
        user_id = convo.user_id
        user_name = convo.user_name or "User"

        await convo.send_message(f"👋 Hello, {user_name}!")

        while True:
            await show_main_menu(convo)

    except Exception as e:
        print(f"Error in conversation: {e}")

async def main():
    manager.start_discovery()
    await agent.start(handle_conversation)

asyncio.run(main())

