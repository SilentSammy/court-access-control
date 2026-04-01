"""
HT16K33 4-Digit 7-Segment Display Driver for MicroPython

Supports 4-digit displays with colon (commonly used for time display)
Communicates via I2C
"""

from machine import I2C, Pin
import time

# 7-segment digit encoding (standard mappings)
# Bit pattern: .GFEDCBA (DP is separate)
DIGITS = {
    # Numbers
    '0': 0x3F, '1': 0x06, '2': 0x5B, '3': 0x4F, '4': 0x66,
    '5': 0x6D, '6': 0x7D, '7': 0x07, '8': 0x7F, '9': 0x6F,
    # Letters (uppercase mapped to most readable representation)
    'A': 0x77,  # All segments except bottom
    'B': 0x7C,  # Lowercase form (more distinguishable)
    'C': 0x39,  # Left bracket shape
    'D': 0x5E,  # Lowercase form (more distinguishable)
    'E': 0x79,  # Full E shape
    'F': 0x71,  # Upper half only
    'G': 0x3D,  # Like C with bottom bar
    'H': 0x76,  # Left + middle + right
    'I': 0x06,  # Just right side (same as 1)
    'J': 0x1E,  # Right + bottom
    'L': 0x38,  # Left + bottom
    'N': 0x54,  # Lowercase n form
    'O': 0x5C,  # Lowercase o (more distinguishable from 0)
    'P': 0x73,  # Upper half + middle
    'Q': 0x67,  # Like 9
    'R': 0x50,  # Lowercase r form
    'S': 0x6D,  # Same as 5
    'T': 0x78,  # Lowercase t form
    'U': 0x3E,  # Like bottom cup
    'Y': 0x6E,  # Y shape
    # Lowercase (for explicit lowercase usage)
    'a': 0x77, 'b': 0x7C, 'c': 0x58, 'd': 0x5E, 'e': 0x79,
    'f': 0x71, 'g': 0x3D, 'h': 0x74, 'i': 0x04, 'j': 0x0E,
    'l': 0x06, 'n': 0x54, 'o': 0x5C, 'p': 0x73, 'q': 0x67,
    'r': 0x50, 's': 0x6D, 't': 0x78, 'u': 0x1C, 'y': 0x6E,
    # Special characters
    ' ': 0x00,  # Blank
    '-': 0x40,  # Middle bar
    '_': 0x08,  # Bottom bar
    '=': 0x48,  # Middle + bottom bars
    '"': 0x22,  # Top quotes
    "'": 0x02,  # Single top quote
    '°': 0x63,  # Degree symbol
    '[': 0x39,  # Left bracket
    ']': 0x0F,  # Right bracket
}

class HT16K33Display:
    """Driver for HT16K33-based 4-digit 7-segment display with colon."""
    
    # HT16K33 Commands
    CMD_OSCILLATOR = 0x21  # Turn on oscillator
    CMD_DISPLAY_ON = 0x81  # Display ON, no blink
    CMD_BRIGHTNESS = 0xE0  # Brightness base (add 0-15 for level)
    
    def __init__(self, i2c, address=0x70):
        """Initialize the display.
        
        Args:
            i2c: I2C object (e.g., I2C(0, scl=Pin(22), sda=Pin(21)))
            address: I2C address (default 0x70)
        """
        self.i2c = i2c
        self.address = address
        self.buffer = bytearray(16)  # 16 bytes for display RAM
        
        # Initialize the display
        self._write_cmd(self.CMD_OSCILLATOR)
        self._write_cmd(self.CMD_DISPLAY_ON)
        self.set_brightness(8)  # Mid brightness
        self.clear()
    
    def _write_cmd(self, cmd):
        """Send a command byte to the display."""
        self.i2c.writeto(self.address, bytes([cmd]))
    
    def _update(self):
        """Send the buffer to the display."""
        # Write to display RAM starting at address 0x00
        data = bytearray([0x00]) + self.buffer
        self.i2c.writeto(self.address, data)
    
    def clear(self):
        """Clear the display."""
        for i in range(16):
            self.buffer[i] = 0x00
        self._update()
    
    def set_brightness(self, level):
        """Set display brightness.
        
        Args:
            level: 0 (dimmest) to 15 (brightest)
        """
        if not 0 <= level <= 15:
            level = max(0, min(15, level))
        self._write_cmd(self.CMD_BRIGHTNESS | level)
    
    def set_colon(self, state):
        """Turn the center colon on or off.
        
        Args:
            state: True to turn on, False to turn off
        """
        # Colon is typically at position 0x04 (between digit 1 and 2)
        if state:
            self.buffer[4] = 0x02  # Turn on colon
        else:
            self.buffer[4] = 0x00  # Turn off colon
        self._update()
    
    def set_digit(self, position, char, dot=False):
        """Set a single digit.
        
        Args:
            position: 0-3 (left to right)
            char: Character to display (see DIGITS mapping)
            dot: True to show decimal point
        """
        if not 0 <= position <= 3:
            return
        
        # Map position to buffer index
        # Typical mapping: digit 0->0, 1->2, 2->6, 3->8
        pos_map = [0, 2, 6, 8]
        buf_index = pos_map[position]
        
        # Get segment pattern
        char = str(char).upper()
        if char in DIGITS:
            pattern = DIGITS[char]
        else:
            # Character not in mapping - show blank
            pattern = 0x00
        
        if dot:
            pattern |= 0x80  # Add decimal point
        
        self.buffer[buf_index] = pattern
        self._update()
    
    def print(self, text, colon=False):
        """Display text on the 4-digit display.
        
        Args:
            text: String to display (up to 4 characters)
            colon: True to show colon
        """
        # Pad or trim to 4 characters
        text = str(text).upper()
        
        # Manual right-justify padding (rjust not available in MicroPython)
        if len(text) < 4:
            text = ' ' * (4 - len(text)) + text
        else:
            text = text[:4]
        
        # Display each character
        for i, char in enumerate(text):
            if i < 4:
                self.set_digit(i, char)
        
        # Set colon
        self.set_colon(colon)
    
    def display_string(self, text):
        """Display a string directly, handling colons automatically.
        
        This function will automatically detect and display colons in strings
        like "12:34". Non-displayable characters are shown as blank spaces.
        
        Args:
            text: String to display (e.g., "12:34", "HELLO", "A-02")
        """
        text = str(text)
        
        # Check if there's a colon in the string
        has_colon = ':' in text
        
        # Remove colon from string
        if has_colon:
            text = text.replace(':', '')
        
        # Convert to uppercase for character lookup
        text_upper = text.upper()
        
        # Pad or trim to 4 characters
        if len(text_upper) < 4:
            text_upper = ' ' * (4 - len(text_upper)) + text_upper
        else:
            text_upper = text_upper[:4]
        
        # Display each character (set_digit handles unknown chars)
        for i, char in enumerate(text_upper):
            if i < 4:
                self.set_digit(i, char)
        
        # Set colon if present in original string
        self.set_colon(has_colon)
    
    def print_number(self, num, decimal_places=0, colon=False):
        """Display a number with optional decimal places.
        
        Args:
            num: Number to display
            decimal_places: Number of decimal places (0-3)
            colon: True to show colon
        """
        if decimal_places > 0:
            # Format with decimal
            format_str = f"{{:4.{decimal_places}f}}"
            text = format_str.format(num)
            
            # Find decimal point position and remove it from string
            if '.' in text:
                dot_pos = text.index('.')
                text = text.replace('.', '')
                
                # Display digits
                for i, char in enumerate(text[:4]):
                    # Show dot on digit before decimal point
                    self.set_digit(i, char, dot=(i == dot_pos - 1))
            else:
                self.print(text, colon)
        else:
            # Integer display
            text = f"{int(num):4d}"
            self.print(text, colon)
    
    def print_time(self, hours, minutes):
        """Display time in HH:MM format with colon.
        
        Args:
            hours: 0-23 (will be formatted as 2 digits)
            minutes: 0-59 (will be formatted as 2 digits)
        """
        # Format as HH:MM
        time_str = f"{hours:02d}{minutes:02d}"
        self.print(time_str, colon=True)
    
    def scroll_text(self, text, delay=0.3):
        """Scroll text across the display.
        
        Args:
            text: Text to scroll
            delay: Delay between scroll steps in seconds
        """
        text = "    " + str(text).upper() + "    "  # Pad with spaces
        for i in range(len(text) - 3):
            self.print(text[i:i+4])
            time.sleep(delay)


def _demo(display):
    """Demo showing display capabilities.
    
    Args:
        display: HT16K33Display instance
    """
    print("HT16K33 Display Demo")
    print("=" * 40)
    
    # Test 1: Numbers
    print("Test 1: Counting 0-9999")
    for i in range(10000):
        display.print_number(i)
        time.sleep(0.001)
    time.sleep(1)
    
    # Test 2: Brightness
    print("Test 2: Brightness levels")
    display.print("8888")
    for level in range(16):
        display.set_brightness(level)
        time.sleep(0.2)
    display.set_brightness(8)  # Reset to mid
    time.sleep(1)
    
    # Test 3: Decimal numbers
    print("Test 3: Decimal numbers")
    for num in [3.14, 2.71, 9.99, 0.01]:
        display.print_number(num, decimal_places=2)
        time.sleep(1)
    
    # Test 4: Time display
    print("Test 4: Time display (12:34)")
    display.print_time(12, 34)
    # Blink colon
    for _ in range(5):
        display.set_colon(False)
        time.sleep(0.5)
        display.set_colon(True)
        time.sleep(0.5)
    
    # Test 5: Hexadecimal
    print("Test 5: Hexadecimal")
    for num in [0xDEAD, 0xBEEF, 0xCAFE, 0xFACE]:
        display.print(f"{num:04X}")
        time.sleep(1)
    
    # Test 6: Scrolling text
    print("Test 6: Scrolling text")
    display.scroll_text("HELLO WORLD", delay=0.2)
    
    # Test 7: Direct string display
    print("Test 7: Direct string display")
    test_strings = ["12:34", "A-01", "HELP", "9:05", "CODE", "b00b"]
    for s in test_strings:
        print(f"  Displaying: {s}")
        display.display_string(s)
        time.sleep(1)
    
    # Test 8: Extended character set
    print("Test 8: Extended characters")
    extended = ["AbCd", "HELo", "good", "Pr09"]
    for s in extended:
        display.display_string(s)
        time.sleep(1)
    
    # Test 9: Clear
    print("Test 9: Clear display")
    display.clear()
    time.sleep(1)
    
    print("Demo complete!")
    print("Try: display.display_string('12:34')")


if __name__ == "__main__":
    # Initialize I2C and display
    # Raspberry Pi Pico W: I2C0 with SCL=GP21, SDA=GP20
    i2c = I2C(0, scl=Pin(21), sda=Pin(20), freq=400000)
    display = HT16K33Display(i2c)
    
    # Run demo - display object remains available in REPL after demo completes
    _demo(display)
