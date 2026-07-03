import os
from wapp.wapp_agent import WAppAgent, build_interactive, create_interactive_list, create_interactive_buttons, Convo
import asyncio

agent = WAppAgent(config_file=os.path.dirname(os.path.abspath(__file__))+'\\wapp.json')

async def handle_conversation(convo: Convo):
    try:
        user_id = convo.user_id
        user_name = convo.user_name


        first_msg = await convo.wait_for_message()
        while True:
            msg = build_interactive(
                header="Hello World",
                body=f"*Hello, {user_name}!*",
                interactive=create_interactive_buttons([ "H", "W", ])
            )
            reply = await convo.prompt(msg)

            if reply.text == "H":
                await convo.send_message("Hello!")
            elif reply.text == "W":
                await convo.send_message("World!")
            else:
                await convo.send_message("You said: " + reply.text)
    
    except Exception as e:
        print(e)

async def main():
    await agent.start(handle_conversation)

asyncio.run(main())

