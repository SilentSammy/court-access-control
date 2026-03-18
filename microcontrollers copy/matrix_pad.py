from machine import Pin
from time import sleep


def set_pins(pins, value):
    for pin in pins:
        pin.value(value)
        sleep(0.00)


class MatrixPad:
    pressedKey = None
    keys = [
        ['1', '2', '3', 'A'],
        ['4', '5', '6', 'B'],
        ['7', '8', '9', 'C'],
        ['*', '0', '#', 'D']
    ]

    def __init__(self, row_pin_nums, col_pin_nums, keys=None):
        self.pad_rows = [Pin(row_pin, Pin.OUT) for row_pin in row_pin_nums]
        self.pad_cols = [Pin(col_pin, Pin.IN, Pin.PULL_DOWN) for col_pin in col_pin_nums]
        self.keys = keys or self.keys

    def read_key(self):
        pad_rows = self.pad_rows
        pad_cols = self.pad_cols
        for i in range(0, len(pad_rows)):
            set_pins(pad_rows, 0)
            pad_rows[i].value(1)
            for j in range(0, len(pad_cols)):
                v = pad_cols[j].value()
                if pad_cols[j].value():
                    if self.pressedKey != (i, j):
                        self.pressedKey = (i, j)
                        return self.pressedKey
                    else:
                        return None
        self.pressedKey = None
        return None
    
    def read_char(self):
        k = self.read_key()
        return self.get_char(k)
    
    def get_char(self, k):
        return self.keys[k[0]][k[1]] if k else None
