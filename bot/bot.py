"""
Generic LLM-based chatbot runtime with MCP integration.

Channel-agnostic: works with any message transport (WhatsApp, terminal, email, etc.)
as long as you provide a conversation context that implements basic message I/O.

Domain-agnostic: business logic lives in the MCP server and BotConfig.
The tool_factory allows complete flexibility in how tools are sourced and configured.
"""
import traceback
import json
import inspect
from dataclasses import dataclass, field
from typing import Callable, Protocol, Any, Optional
from agents import Agent, Runner, function_tool, RunContextWrapper
from collections import deque


# --------------------------------------------------------------------------- #
# Tool Filter Utility
# --------------------------------------------------------------------------- #

def make_tool_filter(allowed_tools: set[str] | None = None):
    """
    Create a tool filter function for MCP servers.
    
    Args:
        allowed_tools: Set of allowed tool names. If None, all tools allowed.
    
    Returns:
        A filter function suitable for MCPServerStreamableHttp.tool_filter
    
    Example:
        # Allow all tools (for admins)
        admin_filter = make_tool_filter(None)
        
        # Allow only specific tools (for non-admins)
        non_admin_filter = make_tool_filter({"get_users_users_get", "get_user_users__user_id__get"})
        
        mcp_server = MCPServerStreamableHttp(..., tool_filter=admin_filter if is_admin else non_admin_filter)
    """
    def tool_filter(ctx, tool) -> bool:
        if allowed_tools is None:
            return True  # No restrictions
        return tool.name in allowed_tools
    return tool_filter




@dataclass
class UserMessage:
    """
    A message received from the user.
    
    Can contain text and optionally media attachments (images, files, audio, etc.).
    Channels can return simple strings or UserMessage objects for richer content.
    """
    text: str
    # Placeholder for future media support
    # media: list[tuple[str, bytes, str]] = field(default_factory=list)
    # Format: [(filename, data, mime_type), ...]


class ConversationContext(Protocol):
    """
    Protocol for conversation contexts - implement this for any channel.
    
    This defines the minimal interface needed for a bot to communicate
    with users through any channel (WhatsApp, terminal, email, etc.)
    """
    
    async def send_message(self, text: str) -> None:
        """Send a text message to the user."""
        ...
    
    async def wait_for_message(self) -> str | UserMessage:
        """
        Wait for and return the next message from the user.
        
        Can return either a simple string (text only) or a UserMessage object
        (for richer content like images, files, etc.).
        """
        ...
    
    @property
    def user_id(self) -> str:
        """Unique identifier for the user in this conversation."""
        ...


class TerminalContext:
    def __init__(self, user_id: str = "terminal_user"):
        self._user_id = user_id
    
    async def send_message(self, text: str) -> None:
        print(f"\n🤖 Assistant: {text}\n")
    
    async def wait_for_message(self) -> str:
        return input("👤 You: ")
    
    @property
    def user_id(self) -> str:
        return self._user_id


@dataclass
class BotConfig:
    """Configuration for creating bots (immutable)."""
    system_prompt: str | Callable[[RunContextWrapper[Any], Agent[Any]], str]
    model: str = "gpt-4o"
    agent_name: str = "Assistant"
    history_size: int | None = 10
    tool_factory: Optional[Callable[[ConversationContext], dict[str, Any]]] = None
    """
    Factory function that builds tools for a conversation.
    
    Signature: async def tool_factory(context: ConversationContext) -> dict
    
    Returns dict with:
        - "mcp_servers": list of MCP server instances (optional, default [])
        - "tools": list of function_tool instances (optional, default [])
    
    If None, no tools or MCP servers are available.
    """
    
    async def create_bot(self, context: ConversationContext) -> "Bot":
        """Create a new bot instance for a conversation."""
        return await Bot.create(self, context)


class Bot:
    """A single conversation instance - encapsulates all state and behavior."""
    
    def __init__(
        self,
        config: BotConfig,
        context: ConversationContext,
        agent: Agent,
        tools: list,
        mcp_servers: list,
        mcp_server_contexts: list
    ):
        self.config = config
        self.context = context
        self.agent = agent
        self.tools = tools
        self.mcp_servers = mcp_servers
        self._mcp_server_contexts = mcp_server_contexts
        self.history = deque(maxlen=config.history_size if config.history_size else None)
    
    @classmethod
    async def create(cls, config: BotConfig, context: ConversationContext) -> "Bot":
        """Factory: create and initialize a new bot."""
        print(f"Creating bot for {context.user_id}")
        
        # Build tools for this conversation
        tool_config = {}
        if config.tool_factory:
            tool_config = await config.tool_factory(context) if inspect.iscoroutinefunction(config.tool_factory) else config.tool_factory(context)
        
        mcp_server_contexts = tool_config.get("mcp_servers", [])
        tools = tool_config.get("tools", [])
        
        # Enter MCP servers
        mcp_servers = []
        for mcp_ctx in mcp_server_contexts:
            entered = await mcp_ctx.__aenter__()
            mcp_servers.append(entered)
        
        # Create agent
        agent = Agent(
            name=config.agent_name,
            instructions=config.system_prompt,
            model=config.model,
            mcp_servers=mcp_servers,
            tools=tools,
        )
        print(f"[AGENT] Created with {len(agent.tools)} tools")
        
        return cls(config, context, agent, tools, mcp_servers, mcp_server_contexts)
    
    def add_to_history(self, content: str, role: str = "user") -> None:
        """Add message to history and trim to max size."""
        self.history.append({"role": role, "content": content})

    async def process_history(self, history: list=None) -> str:
        """
        Run agent on history and return reply without modifying bot's history.
        
        This method is for advanced use cases where the caller wants to manage
        history manually. It executes the agent on the provided history and
        returns only the final output (reply text).
        
        Args:
            history: The message history to run the agent on.
        
        Returns:
            The agent's final output (reply text).
        """
        history = history or self.history
        print(f"[AGENT] Running with {len(self.agent.tools)} function tools + {len(self.mcp_servers)} MCP server(s)")
        result = await Runner.run(self.agent, input=history, context=self.context)
        
        # Debug: Log tool calls
        if hasattr(result, 'messages'):
            for msg in result.messages:
                if hasattr(msg, 'tool_calls') and msg.tool_calls:
                    for tc in msg.tool_calls:
                        print(f"[TOOL CALL] {tc.function.name}({tc.function.arguments})")
                if hasattr(msg, 'tool_call_results') and msg.tool_call_results:
                    for tcr in msg.tool_call_results:
                        content_preview = tcr.content[:200] + "..." if len(tcr.content) > 200 else tcr.content
                        print(f"[TOOL RESULT] {tcr.tool_call_id}: {content_preview}")
        
        return result.final_output
    
    async def process_message(self, text: str) -> str:
        """Process one user message and return response."""
        self.add_to_history(text, "user")
        reply = await self.process_history()
        
        # Add assistant's reply to history
        self.add_to_history(reply, "assistant")
        
        return reply
    
    async def run(self):
        """Run the conversation loop until error or exit."""
        try:
            while True:
                user_msg = await self.context.wait_for_message()
                if not user_msg:
                    continue
                
                # Handle string, UserMessage, or any object with .text attribute
                if isinstance(user_msg, str):
                    text = user_msg
                elif hasattr(user_msg, 'text'):
                    text = user_msg.text
                else:
                    text = str(user_msg)
                
                if not text:
                    continue
                
                response = await self.process_message(text)
                await self.context.send_message(response)
                
        except Exception as e:
            print(f"Error: {e}")
            traceback.print_exc()
            await self.context.send_message("Sorry, something went wrong. Please try again.")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up MCP server resources."""
        for mcp_ctx in reversed(self._mcp_server_contexts):
            try:
                await mcp_ctx.__aexit__(None, None, None)
            except Exception as e:
                print(f"Error closing MCP context: {e}")


async def run_conversation(config: BotConfig, context: ConversationContext):
    """Backward compatibility wrapper - run a conversation using Bot."""
    bot = await config.create_bot(context)
    await bot.run()


# --------------------------------------------------------------------------- #
# Terminal demo
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    from agents import function_tool
    from datetime import datetime
    
    load_dotenv()
    
    # Demo: simple shopping list tools
    shopping_list = ["milk", "eggs", "bread"]
    
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
    
    # Tool factory for terminal demo
    async def terminal_tool_factory(context: ConversationContext) -> dict:
        return {
            "tools": [add_item, remove_item, list_items, clear_list]
        }
    
    # Dynamic system prompt with current time
    def build_terminal_prompt(context, agent) -> str:
        now = datetime.now().strftime("%H:%M:%S")
        return (
            f"You are a helpful shopping list assistant (Current time: {now}). "
            "You can add items, remove items, show the list, and clear it. "
            "Be friendly and concise."
        )
    
    # Configure and run the bot
    config = BotConfig(
        system_prompt=build_terminal_prompt,  # Dynamic prompt updated per-request
        model="gpt-4o-mini",
        tool_factory=terminal_tool_factory,
        agent_name="Shopping Assistant",
        history_size=10,  # Keep last 10 turns
    )
    
    print("=" * 60)
    print("Terminal Bot Demo - Shopping List Assistant")
    print("=" * 60)
    print("Features: History limited to 10 turns, dynamic time-aware prompts")
    print("Type your messages and press Enter. Ctrl+C to exit.\n")
    
    context = TerminalContext()
    
    try:
        asyncio.run(run_conversation(config, context))
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
