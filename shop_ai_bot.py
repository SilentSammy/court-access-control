import os
import asyncio
from datetime import datetime
from agents import function_tool
from wapp.wapp_agent import WAppAgent, Convo
from bot.bot import BotConfig, Bot, RunContextWrapper, ConversationContext

wagent = WAppAgent(config_file=os.path.dirname(os.path.abspath(__file__))+'\\wapp.json')

# Shopping list state (shared across all users)
shopping_list = ["milk", "eggs", "bread"]

# Customers get full access to all tools, couriers have read-only access.
CUSTOMERS = ["50766180742"]

@function_tool
def add_item(item: str) -> str:
    """Add an item to the shopping list."""
    shopping_list.append(item)
    return f"Added '{item}' to the list."

@function_tool
def remove_item(item: str) -> str:
    """Remove an item from the shopping list."""
    if item in shopping_list:
        shopping_list.remove(item)
        return f"Removed '{item}' from the list."
    return f"'{item}' not found in the list."

@function_tool
def list_items() -> str:
    """Show all items in the shopping list."""
    if not shopping_list:
        return "The shopping list is empty."
    return "Shopping list:\n" + "\n".join(f"• {item}" for item in shopping_list)

@function_tool
def clear_list() -> str:
    """Clear the entire shopping list."""
    count = len(shopping_list)
    shopping_list.clear()
    return f"Cleared {count} item(s) from the list."

def build_system_prompt(context, agent=None) -> str:
    now = datetime.now().strftime("%H:%M:%S")
    convo = context.context
    is_customer = convo.user_id in CUSTOMERS
    capabilities = "You can add items, remove items, show the list, and clear it." if is_customer else "You can only view the shopping list."
    return (
        f"You are a helpful shopping list assistant.\n"
        f"{capabilities}\n"
        "Be friendly and concise.\n"
        "\n"
        f"Current time: {now}.\n"
        f"User ID: {convo.user_id}\n"
        f"User Role: {'Customer' if is_customer else 'Courier'}\n"
    )

def tool_factory(context: ConversationContext) -> dict:
    convo = context
    if convo.user_id in CUSTOMERS:
        return {"tools": [add_item, remove_item, list_items, clear_list]}
    return {"tools": [list_items]}

config = BotConfig(
    system_prompt=build_system_prompt,
    tool_factory=tool_factory,
    model="gpt-4o-mini",
    agent_name="Shopping Assistant",
    history_size=10,
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

if __name__ == "__main__":
    asyncio.run(main())

