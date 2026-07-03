import os
from wapp.wapp_agent import WAppAgent, build_interactive, create_interactive_list, Convo
import asyncio

agent = WAppAgent(config_file=os.path.dirname(os.path.abspath(__file__))+'\\wapp.json')

# Shopping list state (shared across all users)
shopping_list = ["milk", "eggs", "bread"]

# Customers get full access, couriers have read-only access
CUSTOMERS = ["50766180742"]

async def show_main_menu(convo: Convo, is_customer: bool):
    """Display main menu and process user's choice."""
    if is_customer:
        choices = ["📊 View List", "➕ Add Item", "➖ Remove Item", "🗑️ Clear All"]
    else:
        choices = ["📊 View List"]
    
    msg = build_interactive(
        header="Shopping List",
        body="*What would you like to do?*",
        interactive=create_interactive_list("Select", choices)
    )
    choice = (await convo.prompt(msg)).text
    
    if choice == choices[0]:
        await show_list(convo)
    elif is_customer and choice == choices[1]:
        await add_item_menu(convo)
    elif is_customer and choice == choices[2]:
        await remove_item_menu(convo)
    elif is_customer and choice == choices[3]:
        await clear_all_menu(convo)

async def show_list(convo: Convo):
    """Display current shopping list."""
    if not shopping_list:
        await convo.send_message("📭 The shopping list is empty.")
    else:
        items = "\n".join(f"• {item}" for item in shopping_list)
        await convo.send_message(f"📋 *Shopping List:*\n{items}")

async def add_item_menu(convo: Convo):
    """Add item to shopping list."""
    await convo.send_message("What item would you like to add?")
    msg = await convo.wait_for_message()
    item = msg.text.strip()
    if item:
        shopping_list.append(item)
        await convo.send_message(f"✅ Added '{item}' to the list.")
    else:
        await convo.send_message("❌ No item provided.")

async def remove_item_menu(convo: Convo):
    """Remove item from shopping list."""
    if not shopping_list:
        await convo.send_message("📭 The list is empty, nothing to remove.")
        return
    
    msg = build_interactive(
        header="Remove Item",
        body="*Select an item to remove:*",
        interactive=create_interactive_list("Select", [f"• {item}" for item in shopping_list])
    )
    reply = await convo.prompt(msg)
    item_display = reply.text
    # Extract item name from display format "• {item}"
    item = item_display.replace("• ", "") if item_display else None
    if item and item in shopping_list:
        shopping_list.remove(item)
        await convo.send_message(f"✅ Removed '{item}' from the list.")
    else:
        await convo.send_message(f"❌ '{item}' not found in the list.")

async def clear_all_menu(convo: Convo):
    """Clear entire shopping list."""
    count = len(shopping_list)
    shopping_list.clear()
    await convo.send_message(f"✅ Cleared {count} item(s) from the list.")

async def handle_conversation(convo: Convo):
    try:
        _ = await convo.wait_for_message() # discard first message, just to start the conversation
        user_id = convo.user_id
        user_name = convo.user_name
        is_customer = user_id in CUSTOMERS
        role = "Customer" if is_customer else "Courier"

        await convo.send_message(f"👋 Welcome, {user_name}! ({role})")

        while True:
            await show_main_menu(convo, is_customer)
    
    except Exception as e:
        print(e)
        await convo.send_message(f"❌ Error: {str(e)}")

async def main():
    await agent.start(handle_conversation)

if __name__ == "__main__":
    asyncio.run(main())

