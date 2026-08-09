import os

from wapp.wapp_agent import WAppAgent, build_interactive, create_interactive_list, create_interactive_buttons, Convo
from bot.wapp_tools import send_buttons, send_list
import asyncio
from bot.bot import BotConfig, Bot, Agent, RunContextWrapper
from datetime import datetime

wagent = WAppAgent(config_file=os.path.dirname(os.path.abspath(__file__))+'\\wapp.json')

def build_system_prompt(context, agent=None) -> str:
    SYSTEM_PROMPT = (
        "You are just a test bot that is used to test Whatsapp integration. If you are seeing this message, it means the Whatsapp integration is working.\n"
        "You can also use the interactive buttons and lists to test the interactive features.\n"
        "\n"
        "CURRENT CONTEXT:\n"
        "  - User ID: {user_id}\n"
        "  - User Name: {user_name}\n"
        "  - Time: {current_time}\n"
    )

    convo = context.context
    return SYSTEM_PROMPT.format(
        user_id=convo.user_id,
        user_name=convo.user_name,
        current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

def tool_factory(context: RunContextWrapper[Convo]) -> dict:
    return { "tools": [send_buttons, send_list] }

config = BotConfig(
    system_prompt=build_system_prompt,
    tool_factory=tool_factory,
    model="gpt-4o",
    agent_name="Test Bot",
    history_size=20,
)

async def handle_conversation(convo: Convo):
    try:
        bot = await Bot.create(config, convo)

        while True:
            user_msg = await convo.wait_for_message()
            bot.add_to_history(user_msg.text, role="user")
            response = await bot.process_history()

            await convo.send_message(response)

            bot.add_to_history(response, role="assistant")
    
    except Exception as e:
        print(e)
        await convo.send_message(f"❌ Error: {str(e)}")
    
    finally:
        await bot.cleanup()

async def main():
    await wagent.start(handle_conversation)

asyncio.run(main())

