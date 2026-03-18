import os
import traceback
import wapp_agent as wapp_agent
from wapp_agent import WAppAgent, Convo
import asyncio
from facility import FacilityManager

# Initialize facility manager (config is loaded from facility_config.json)
facility = FacilityManager()

async def handle_conversation(convo: Convo):
    def create_menu():
        """Create the main menu options."""
        return wapp_agent.create_interactive_list("Select", [
            "Turn ON lights",
            "Turn OFF lights", 
            "Check room status"
        ])
    
    def create_room_options():
        """Create room selection options."""
        return wapp_agent.create_interactive_list("Select", list(facility.rooms.keys()) + ["Cancel"])
    
    async def control_lights(state):
        """Handle light control for a selected room."""
        # Prompt for room selection
        msg = wapp_agent.build_interactive(
            header="Control Lights",
            body=f"Select a room to turn {'ON' if state else 'OFF'}",
            interactive=create_room_options()
        )
        reply = await convo.prompt(msg)
        
        if reply.text == "Cancel" or reply.text not in facility.rooms:
            return
        
        # Control the lights
        room_id = reply.text
        result = await facility.control_lights(room_id, state)
        
        # Send confirmation
        status = "✅ ON" if state else "⭕ OFF"
        await convo.send_message(
            f"*Room {result['room']} lights*: {status}\n"
            f"_Action: {result['action']}_"
        )
    
    async def check_status():
        """Check the status of a selected room."""
        # Prompt for room selection
        msg = wapp_agent.build_interactive(
            header="Room Status",
            body="Select a room to check status",
            interactive=create_room_options()
        )
        reply = await convo.prompt(msg)
        
        if reply.text == "Cancel" or reply.text not in facility.rooms:
            return
        
        # Get room status
        room_id = reply.text
        result = await facility.get_room_status(room_id)
        
        # Send status
        light_icon = "✅" if result['light'] == "on" else "⭕"
        await convo.send_message(
            f"*Room {result['room']} Status*\n"
            f"Lights: {light_icon} {result['light'].upper()}"
        )
    
    # Menu handlers
    menu_handlers = {
        "Turn ON lights": lambda: control_lights(True),
        "Turn OFF lights": lambda: control_lights(False),
        "Check room status": check_status
    }
    
    # Start the conversation loop
    while True:
        try:
            # Show main menu
            menu_msg = wapp_agent.build_interactive(
                header="Facility Control",
                body="*Admin Panel*\nWhat would you like to do?",
                interactive=create_menu()
            )
            
            msg = await convo.prompt(menu_msg)
            
            # Handle menu selection
            if msg.text in menu_handlers:
                await menu_handlers[msg.text]()
            
        except Exception as e:
            traceback.print_exc()
            print(e)

# Create a WAppAgent object
agent = WAppAgent(config_file=os.path.dirname(os.path.abspath(__file__))+'\\wapp.json')

# Start the agent and handle conversations
asyncio.run(agent.start(handle_conversation))
