"""
WhatsApp-specific bot configuration and tools.

Builds on the generic bot.py infrastructure by providing WhatsApp-native UI tools (buttons, lists, photos).
"""
import os
from typing import Optional

from agents import function_tool, RunContextWrapper

from wapp.wapp_agent import (
    build_interactive,
    create_interactive_buttons,
    create_interactive_list,
    build_media,
)
from wapp.wapp_agent import Convo


# --------------------------------------------------------------------------- #
# WhatsApp-specific UI tools
# --------------------------------------------------------------------------- #

@function_tool
async def send_buttons(ctx: RunContextWrapper[Convo], body: str, buttons: list[str]) -> str:
    """
    Send up to 3 tappable reply buttons to the user. Use for small, binary-ish choices
    such as Yes/No/Cancel or action confirmations.
    WhatsApp enforces: max 3 buttons, titles truncated to 20 characters.
    Returns the title of the button the user tapped.
    """
    buttons = [b[:20] for b in buttons[:3]]
    msg = build_interactive(body=body, interactive=create_interactive_buttons(buttons))
    await ctx.context.send_message(msg)
    response = await ctx.context.wait_for_message()
    # Handle both ConvoMessage and string returns
    return response.text if hasattr(response, 'text') else response


@function_tool
async def send_list(ctx: RunContextWrapper[Convo], button_label: str, body: str, options: list[str]) -> str:
    """
    Send a tappable scrollable list menu to the user. Use when there are 4 to 10 options.
    WhatsApp enforces: max 10 rows, option titles truncated to 24 characters.
    Returns the title of the option the user selected.
    """
    options = [o[:24] for o in options[:10]]
    msg = build_interactive(body=body, interactive=create_interactive_list(button_label, options))
    await ctx.context.send_message(msg)
    response = await ctx.context.wait_for_message()
    # Handle both ConvoMessage and string returns
    return response.text if hasattr(response, 'text') else response


def make_send_photo(media_dir: str, dir_label: Optional[str] = None):
    """
    Build a send_photo tool bound to a specific media directory with security restrictions.
    
    Args:
        media_dir: Path or glob pattern for allowed photos (e.g., 'data/photos' or 'data/photos/*.jpg').
                   Supports wildcards to restrict file types.
        dir_label: Optional label for the directory (e.g., 'temp', 'user_photos').
                   If provided, creates tool named 'send_photo_{label}'.
                   If None, creates tool named 'send_photo'.
    
    Security:
        - Blocks path traversal attacks (../ in filenames)
        - Blocks absolute paths
        - Only allows files matching the media_dir pattern
    """
    import glob
    from pathlib import Path
    
    # Parse base directory and pattern from media_dir
    # If it's a glob pattern, extract the base directory
    media_path = Path(media_dir)
    if '*' in media_dir or '?' in media_dir:
        # Glob pattern - find the base directory without wildcards
        parts = media_path.parts
        base_parts = []
        for part in parts:
            if '*' in part or '?' in part:
                break
            base_parts.append(part)
        base_dir = Path(*base_parts) if base_parts else Path('.')
        pattern = media_dir
    else:
        # Regular directory - allow any file in it
        base_dir = media_path
        pattern = str(media_path / '*')
    
    # Generate tool name and description based on dir_label
    tool_name = f"send_photo_{dir_label}" if dir_label else "send_photo"
    dir_description = f"the {dir_label} folder" if dir_label else "the media folder"
    tool_description = f"Send a photo to the user by filename from {dir_description}. Use sparingly - avoid sending too many pictures at once."

    @function_tool(name_override=tool_name, description_override=tool_description)
    async def send_photo(ctx: RunContextWrapper[Convo], filename: str) -> str:
        """Send a photo to the user by filename (e.g. 'person1.jpg')."""
        # Security: Block path traversal attempts
        if '..' in filename:
            return "Security error: Path traversal not allowed."
        
        # Security: Block absolute paths
        if os.path.isabs(filename) or filename.startswith('/') or filename.startswith('\\'):
            return "Security error: Absolute paths not allowed. Use filename only."
        
        # Construct full path
        photo_path = base_dir / filename
        
        # Security: Verify the resolved path matches the allowed pattern
        allowed_files = set(glob.glob(pattern, recursive=False))
        if str(photo_path.resolve()) not in {str(Path(f).resolve()) for f in allowed_files}:
            return f"Photo '{filename}' not found in {dir_description} or not allowed by pattern."
        
        if not photo_path.exists():
            return f"Photo '{filename}' not found in {dir_description}."

        media_id = await ctx.context.agent.upload_media(str(photo_path))
        await ctx.context.send_message(build_media(media_id))
        return f"Photo '{filename}' sent successfully from {dir_description}."

    return send_photo

