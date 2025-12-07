from machine import Pin
from time import sleep_us

def split_string(string, n):
  split_string = []
  for i in range(0, len(string), n):
    split_string.append(string[i:i + n])
  return split_string

def pad_string_to_length(s, length):
    """Pad the string 's' to the specified 'length' with spaces."""
    return s + ' ' * (length - len(s))

class LCD:
    def __init__(self, RS, E, D4, D5, D6, D7):
        self.p_rs = Pin(RS, Pin.OUT, value=0)
        self.p_e = Pin(E, Pin.OUT, value=0)
        self.p_d4 = Pin(D4, Pin.OUT, value=0)
        self.p_d5 = Pin(D5, Pin.OUT, value=0)
        self.p_d6 = Pin(D6, Pin.OUT, value=0)
        self.p_d7 = Pin(D7, Pin.OUT, value=0)
        self.port(0x00)
        sleep_us(20000)
        self.cmd(0x03)
        sleep_us(5000)
        self.cmd(0x03)
        sleep_us(11000)
        self.cmd(0x03)
        self.cmd(0x02)
        self.cmd(0x02)
        self.cmd(0x08)
        self.cmd(0x00)
        self.cmd(0x0C)
        self.cmd(0x00)
        self.cmd(0x06)
        self.clear()
        self.prev_display = ""

    def port(self, a):
        if (a & 1):
            self.p_d4.value(1)
        else:
            self.p_d4.value(0)
        if (a & 2):
            self.p_d5.value(1)
        else:
            self.p_d5.value(0)
        if (a & 4):
            self.p_d6.value(1)
        else:
            self.p_d6.value(0)
        if (a & 8):
            self.p_d7.value(1)
        else:
            self.p_d7.value(0)

    def cmd(self, com):
        self.p_rs.value(0)
        self.port(com)
        self.p_e.value(1)
        sleep_us(4000)
        self.p_e.value(0)

    def clear(self):
        self.cmd(0)
        self.cmd(1)

    def move_to(self, col, row):
        if row == 0:
            temp = 0x80 + col
            z = temp >> 4
            y = temp & 0x0F
            self.cmd(z)
            self.cmd(y)

        elif row == 1:
            temp = 0xC0 + col
            z = temp >> 4
            y = temp & 0x0F
            self.cmd(z)
            self.cmd(y)

        elif row == 2:
            temp = 0x94 + col
            z = temp >> 4
            y = temp & 0x0F
            self.cmd(z)
            self.cmd(y)

        elif row == 3:
            temp = 0xD4 + col
            z = temp >> 4
            y = temp & 0x0F
            self.cmd(z)
            self.cmd(y)

    def putchar(self, c):
        temp = ord(c) & 0x0F
        y = ord(c) & 0xF0
        self.p_rs.value(1)
        self.port(y >> 4)
        self.p_e.value(1)
        sleep_us(40)
        self.p_e.value(0)
        self.port(temp)
        self.p_e.value(1)
        sleep_us(40)
        self.p_e.value(0)

    def putstr(self, st):
        for x in st:
            self.putchar(x)

    def shift_left(self):
        self.cmd(0x01)
        self.cmd(0x08)

    def shift_right(self):
        self.cmd(0x01)
        self.cmd(0x0C)

    def blink(self):
        self.cmd(0x00)
        self.cmd(0x0F)

    def no_blink(self):
        self.cmd(0x00)
        self.cmd(0x0C)

    def cgram_init(self):
        self.cmd(0x04)
        self.cmd(0x00)

    def cgram_close(self):
        self.cmd(0x00)
        self.cmd(0x02)

    def cgram_create_char(self, add, chardata):
        if add == 0:
            for x in range(0,8):
                self.cgram_putc(chardata[x])
        elif add == 1:
            for x in range(8,16):
                self.cgram_putc(chardata[x-8])
        elif add == 2:
            for x in range(16,24):
                self.cgram_putc(chardata[x-16])
        elif add == 3:
            for x in range(24,32):
                self.cgram_putc(chardata[x-24])
        elif add == 4:
            for x in range(32,40):
                self.cgram_putc(chardata[x-32])
        elif add == 5:
            for x in range(40,48):
                self.cgram_putc(chardata[x-40])
        elif add == 6:
            for x in range(48,56):
                self.cgram_putc(chardata[x-48])
        elif add == 7:
            for x in range(56,64):
                self.cgram_putc(chardata[x-56])

    def cgram_putc(self, c):
        temp = c & 0x0F
        y = c & 0xF0
        self.p_rs.value(1)
        self.port(y >> 4)
        self.p_e.value(1)
        sleep_us(40)
        self.p_e.value(0)
        self.port(temp)
        self.p_e.value(1)
        sleep_us(40)
        self.p_e.value(0)

    def overwrite_text(self, text):
        self.clear()
        lines = text.splitlines()

        for i in range(len(lines)):
            self.move_to(0,i)
            self.putstr(lines[i])

    def update_display(self, new_string):
        # Split the strings into lines
        new_lines = new_string.split('\n')
        prev_lines = self.prev_display.split('\n')

        # Pad the list of lines to ensure equal length
        max_lines = max(len(new_lines), len(prev_lines))
        new_lines += [''] * (max_lines - len(new_lines))
        prev_lines += [''] * (max_lines - len(prev_lines))

        # Update line by line
        for line_num, (new_line, prev_line) in enumerate(zip(new_lines, prev_lines)):
            # Determine the length to pad to
            max_length = max(len(new_line), len(prev_line))
            new_line_padded = pad_string_to_length(new_line, max_length)
            prev_line_padded = pad_string_to_length(prev_line, max_length)

            start_index = None
            accumulated_chars = ''

            # Accumulate and update different characters
            for i, (new_char, old_char) in enumerate(zip(new_line_padded, prev_line_padded)):
                if new_char != old_char:
                    if start_index is None:
                        start_index = i
                    accumulated_chars += new_char
                elif accumulated_chars:
                    self.move_to(start_index, line_num)
                    self.putstr(accumulated_chars)
                    start_index = None
                    accumulated_chars = ''

            # Handle any remaining accumulated characters
            if accumulated_chars:
                self.move_to(start_index, line_num)
                self.putstr(accumulated_chars)

        # Update the stored previous display string
        self.prev_display = new_string