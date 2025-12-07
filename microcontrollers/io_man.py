import asyncio

class IOManager:
    """
    Hardware-agnostic I/O manager for pseudo-synchronous input/output operations.
    Abstracts input polling and output display functions.
    """
    
    def __init__(self, input_func, output_func):
        """
        Initialize IOManager with hardware-specific functions.
        
        Args:
            input_func: Function that returns a character or None (e.g., keypad.read_char)
            output_func: Function that accepts a string for display (e.g., display.overwrite)
        """
        self.input_func = input_func
        self.output_func = output_func
        self.input_buffer = []  # Buffer for unprocessed characters
        self._interrupted = False  # Simple interrupt flag
        self.on_char_received = None  # Optional callback: on_char_received(char)
    
    async def read_char(self, timeout=None):
        """
        Asynchronously wait for a single character input.
        
        Args:
            timeout: Maximum time to wait in seconds (None for infinite wait)
            
        Returns:
            Character if input received within timeout, None if timeout exceeded
            
        Raises:
            KeyboardInterrupt: If interrupt() was called
        """
        if timeout is None:
            # Infinite wait (original behavior)
            while True:
                # Check for interrupt request
                if self._interrupted:
                    self._interrupted = False  # Reset flag
                    raise KeyboardInterrupt()
                
                # Always check buffer first
                if self.input_buffer:
                    char = self.input_buffer.pop(0)
                    if self.on_char_received:
                        self.on_char_received(char)
                    return char
                
                char = self.input_func()
                if char:
                    if self.on_char_received:
                        self.on_char_received(char)
                    return char
                await asyncio.sleep(0.05)
        else:
            # Wait with timeout
            elapsed_cycles = 0
            timeout_cycles = int(timeout / 0.05)
            
            while elapsed_cycles < timeout_cycles:
                # Check for interrupt request
                if self._interrupted:
                    self._interrupted = False  # Reset flag
                    raise KeyboardInterrupt()
                
                # Always check buffer first
                if self.input_buffer:
                    char = self.input_buffer.pop(0)
                    if self.on_char_received:
                        self.on_char_received(char)
                    return char
                
                char = self.input_func()
                if char:
                    if self.on_char_received:
                        self.on_char_received(char)
                    return char
                await asyncio.sleep(0.05)
                elapsed_cycles += 1
            
            return None  # Timeout exceeded
    
    async def read_input(self, prompt_template=None, timeout=2.0, max_length=None):
        """
        Asynchronously read input with optional prompt and live feedback.
        
        Args:
            prompt_template: Optional string template for display
                - None: Acts like read_string (no display, just accumulate input)
                - String without {0}/{}: Display prompt once at start
                - String with {0}/{}: Update display with user input as they type
            timeout: Seconds of idle time before completing input
            max_length: Optional maximum number of characters (None for unlimited)
            
        Returns:
            Complete user input string
            
        Examples:
            # Like read_string - no prompt, just collect input
            user_input = await io.read_input()
            
            # Static prompt - display once
            user_input = await io.read_input("Enter your name:")
            
            # Live feedback - update as user types
            user_input = await io.read_input("Name: {0}")
            
            # With character limit
            pin = await io.read_input("PIN: {0}", max_length=4)
        """
        user_input = ""
        
        # Determine display mode based on prompt_template
        if prompt_template is None:
            # Mode 1: No prompt - just like read_string
            display_mode = "none"
        elif "{0}" in prompt_template or "{}" in prompt_template:
            # Mode 3: Live feedback with placeholder
            display_mode = "live"
            self.output_func(prompt_template.format(user_input))
        else:
            # Mode 2: Static prompt - display once
            display_mode = "static"
            self.output_func(prompt_template)
        
        while True:
            # Check if max_length reached
            if max_length is not None and len(user_input) >= max_length:
                break
            
            char = await self.read_char(timeout=timeout)
            if char is None:
                # Timeout reached - return accumulated input
                break
            
            user_input += char
            
            # Update display if in live feedback mode
            if display_mode == "live":
                self.output_func(prompt_template.format(user_input))
            
            # Check again if we just hit max_length
            if max_length is not None and len(user_input) >= max_length:
                break
        
        return user_input

    def push_char(self, char):
        """Push a character into the input buffer for later reading."""
        self.input_buffer.append(char)
    
    def peek_char(self):
        """
        Check if any character is available without consuming it.
        
        Returns:
            Character if available, None otherwise
        """
        if self.input_buffer:
            return self.input_buffer[0]
        
        # Check hardware without blocking
        char = self.input_func()
        if char:
            self.input_buffer.append(char)
            return char
        return None
    
    def interrupt(self):
        """
        Interrupt any ongoing read_char/read_input operation.
        Used to wake up blocking calls when external state changes.
        """
        self._interrupted = True
        self.input_buffer.clear()  # Clear any buffered input
    
    def display(self, text):
        """Synchronously display text (convenience wrapper)."""
        self.output_func(text)
