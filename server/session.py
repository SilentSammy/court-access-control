import math
import sys


class Timestamp(int):
    """Represents a Unix timestamp. Compatible with CPython and MicroPython."""
    SYSTEM_TIMEZONE = 0
    DISPLAY_TIMEZONE = 0
    MIN = 60
    HOUR = 60 * MIN
    DAY = 24 * HOUR

    def format(self, fmt="%Y-%m-%d %H:%M:%S"):
        time = self + Timestamp.HOUR * Timestamp.DISPLAY_TIMEZONE
        if sys.implementation.name == "micropython":
            import utime
            dt = utime.localtime(time)
            return fmt.replace('%Y', '{:04}'.format(dt[0])).replace('%m', '{:02}'.format(dt[1])).replace('%d', '{:02}'.format(dt[2])).replace('%H', '{:02}'.format(dt[3])).replace('%M', '{:02}'.format(dt[4])).replace('%S', '{:02}'.format(dt[5]))
        else:
            from datetime import datetime
            dt = datetime.fromtimestamp(time)
            return dt.strftime(fmt)

    @staticmethod
    def from_datetime(*args):
        if sys.implementation.name == "micropython":
            import utime
            args += (0,) * (9 - len(args))
            timestamp = utime.mktime(args)
        else:  # CPython
            import datetime
            dt = datetime.datetime(*args)
            timestamp = int(dt.timestamp())
        return Timestamp(timestamp)

    @staticmethod
    def now(tz_offset=None):
        if tz_offset is None:
            tz_offset = Timestamp.SYSTEM_TIMEZONE
        if sys.implementation.name == "micropython":
            import utime
            return Timestamp(utime.time() - tz_offset*3600)
        else:  # CPython
            import time
            return Timestamp(time.time() + tz_offset*3600)

    def breakdown(self):
        if sys.implementation.name == "micropython":
            import utime
            dt = utime.localtime(self)
            return dt[:6]  # return year, month, day, hour, minute, second
        else:  # CPython
            from datetime import datetime
            dt = datetime.fromtimestamp(self)
            return dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second

    @property
    def minutes(self):
        return self // 60

class Encoder:
    """Converts an int to a padded base-n string and vice-versa, using a custom alphabet."""
    def __init__(self, base, ceil=None):
        """
        Args:
            base (int): The base to use for encoding and decoding.
            ceil (int): The maximum expected value to encode. This determines the length of the padded string.
        """
        self.base = base
        self.ceil = ceil
        self.alphabet = [str(i) for i in range(10)] + [chr(i) for i in range(65, 90)]  # TODO:replace E and F with * and # (after instantiation)

    def encode(self, num, z_fill=True):
        base_n_num = ""
        while num:
            num, i = divmod(num, self.base)
            base_n_num = self.alphabet[i] + base_n_num
        if z_fill:
            max_digits = len(self.encode(self.ceil - 1, False))
            base_n_num = self.alphabet[0] * (max_digits - len(base_n_num)) + base_n_num
        return base_n_num or self.alphabet[0]  # Return '0' if input num is 0

    def decode(self, base_n_num):
        return int(base_n_num, self.base)

class Cipher:
    """Can encrypt and decrypt an integer value using a reversible cipher."""
    def __init__(self, ceil, mult=None, sum=None):
        self._ceil = Cipher.largest_prime_below(ceil)
        self._mult = mult if mult is not None else Cipher.largest_prime_below(ceil*0.4)
        self._sum = sum if sum is not None else Cipher.largest_prime_below(ceil*0.2)

    def __str__(self):
        return f"{self._ceil}, {self._mult}, {self._sum}"

    def cipher(self, value):
        if value >= self._ceil:
            return value
        value *= self._mult
        value += self._sum
        value = value % self._ceil
        return value

    def decipher(self, value):
        if value >= self._ceil:
            return value

        value -= self._sum
        value = Cipher.reverse_op(value, self._mult, self._ceil)
        return value

    @staticmethod
    def is_prime(n):
        if n <= 1:
            return False
        for i in range(2, int(n**0.5) + 1):
            if n % i == 0:
                return False
        return True

    @staticmethod
    def largest_prime_below(n):
        n = int(n)
        for num in range(n, 1, -1):
            if Cipher.is_prime(num):
                return num
        return None

    @staticmethod
    def multiplicative_inverse(m, n):
        # Uses Extended Euclidean Algorithm
        def extended_gcd(a, b):
            if a == 0:
                return b, 0, 1
            else:
                g, x, y = extended_gcd(b % a, a)
                return g, y - (b // a) * x, x

        _, inv, _ = extended_gcd(m, n)
        return inv % n

    @staticmethod
    def reverse_op(result, m, n):
        m_inv = Cipher.multiplicative_inverse(m, n)
        return (result * m_inv) % n

class IntPacker:
    """This class is used to pack and unpack multiple
    zero-based integer values into and from a
    single zero-based integer value."""
    def __init__(self, *sizes):
        self.sizes = sizes
        self.multipliers = IntPacker._calculate_multipliers(sizes)
    
    @staticmethod
    def _calculate_multipliers(sizes):
        # we start with a multiplier of 1 and then multiply it by each size in reverse order
        multipliers = [1]

        # we iterate through the sizes (excluding the first one), in reverse order
        for size in reversed(sizes[1:]):
            multipliers.append(multipliers[-1] * size)
        return list(reversed(multipliers))
    
    def pack(self, *values, wrap_first=True):
        # validate the number of values
        if len(values) != len(self.sizes):
            raise ValueError("Number of values does not match the number of specified sizes.")
        
        # start with an empty int
        packed_value = 0

        # zip the values, multipliers and sizes
        zipped = list(zip(values, self.multipliers, self.sizes))
        if not wrap_first:
            packed_value += zipped[0][0] * zipped[0][1]
            zipped = zipped[1:]
        for value, multiplier, size in zipped:
            # add the value multiplied by the multiplier to the packed value
            packed_value += (value % size) * multiplier
        return packed_value
    
    def unpack(self, packed_value):
        # we start with an empty list of values
        values = []
        
        # zip the multipliers and sizes
        zipped = list(zip(self.multipliers, self.sizes))[1:]
        values.append(packed_value // self.multipliers[0])
        for multiplier, size in zipped:
            # unpack the value
            value = (packed_value // multiplier)
            value %= size
            values.append(value)
        return tuple(values)

class Session:
    BASE = 10

    START_DIGITS = 4
    SPAN_DIGITS = 3
    ROOM_DIGITS = 1

    TOTAL_DIGITS = START_DIGITS + SPAN_DIGITS + ROOM_DIGITS
    
    START_CEIL = BASE ** START_DIGITS
    SPAN_CEIL = BASE ** SPAN_DIGITS
    ROOM_CEIL = BASE ** ROOM_DIGITS
    
    TOTAL_CEIL = BASE ** TOTAL_DIGITS

    MIN_SPAN = 0
    ENTRY_MARGIN = 1

    CIPHER = Cipher(TOTAL_CEIL)
    ENCODER = Encoder(BASE, TOTAL_CEIL)
    PACKER = IntPacker(START_CEIL, SPAN_CEIL, ROOM_CEIL)

    def __init__(self, start: Timestamp, span: int, room: int = 0):
        self.start = Timestamp(start)
        self.span = span
        self.room = room

    def __str__(self):
        return f"Start: {self.start.format('%Y-%m-%d %H:%M')}, Minutes: {self.span}, Room: {self.room}"

    def __repr__(self):
        # return f"s:{self.start.minutes} d:{self.span} r:{self.room}"
        return f"Session(Timestamp({self.start.minutes}*Timestamp.MIN), {self.span}, {self.room})"

    @property
    def span_hrs(self):
        return self.span / 60

    @property
    def end(self):
        return self.start + self.span*Timestamp.MIN

    @property
    def code(self):
        """This integer is a lossy encoding of the session's start time, span and room."""
        return Session.PACKER.pack(self.start.minutes, self.span, self.room)

    @property
    def full_code(self):
        """This integer is a lossless encoding of the session's start time, but lossy span and room."""
        return Session.PACKER.pack(self.start.minutes, self.span, self.room, wrap_first=False)

    @property
    def passcode(self):
        """An encrypted version of the session's partial code. It's safe to share with users (allegedly)."""
        return Session.ENCODER.encode(Session.CIPHER.cipher(self.code))

    def has_ended(self):
        # TODO: use time_left and include allow a reference start time to be passed
        """Returns True if the session has ended."""
        return Timestamp.now() > self.end
    
    def has_started(self):
        """Returns True if the time_until method returns 0 or less."""
        return (-self.time_until()) <= 0

    def time_until(self):
        """Returns the time until the session is allowed to start, in negative seconds. If the session has already started, returns 0."""
        current_time = Timestamp.now()
        start = self.start - Timestamp.MIN * Session.ENTRY_MARGIN
        return min(current_time - start, 0)

    def time_left(self, start_time:Timestamp=None):
        """Returns the duration of the session, capped to not exceed the end time. Optionally, a start time can be provided."""
        current_time = Timestamp.now()

        # we calculate the end time by adding the span to the start time
        end = min(start_time + self.span*Timestamp.MIN, self.end)

        # we return the session's span, capped to not extend past the end time
        return max(min(end - current_time, self.span*Timestamp.MIN), 0)

    def conflicts_with(self, other):
        """Returns True if this session conflicts with another session."""
        if self.room != other.room: # if the rooms are different, there's no conflict
            return False

        # if the sessions overlap, there's a conflict
        return self.start < other.end and self.end > other.start

    @staticmethod
    def from_code(code):
        """Returns a new Session object from a code. Both types of codes are supported."""
        # unpack code
        start, span, room = Session.PACKER.unpack(code)

        # ensure that span values below the minimum become values above the ceil
        span = ((span - Session.MIN_SPAN) % Session.SPAN_CEIL) + Session.MIN_SPAN

        # if the code is a partial code, complete the timestamp
        if code < Session.TOTAL_CEIL:
            start = Session.complete_timestamp(start, span)
        else:
            start = Timestamp(start*Timestamp.MIN)

        # create session
        return Session(start, span, room)
    
    @staticmethod
    def from_passcode(passcode):
        """Returns a new Session object from a passcode."""
        return Session.from_code(Session.CIPHER.decipher(Session.ENCODER.decode(passcode)))

    @staticmethod
    def complete_timestamp(part_mins, margin):
        # the reference timestamp is the current time in minutes minus the margin
        ref = Timestamp.now().minutes - margin + 1

        # we use magic (i forgor 💀 how this works) to complete the timestamp's missing digits to the closest future timestamp
        difference = ref - part_mins
        division_result = difference / Session.START_CEIL
        ceil_result = math.ceil(division_result)
        multiplied = ceil_result * Session.START_CEIL
        found = multiplied + part_mins

        # return the timestamp
        return Timestamp(found*Timestamp.MIN)


if __name__ == "__main__" and sys.implementation.name == "cpython":

    raise SystemExit

    from datetime import datetime, timedelta
    import time

    # we print the codes of RANDOM sessions for the next week
    print(Session(start=datetime(2024, 2, 27, 8, 0).timestamp(), span=120, room=0).full_code)
    print(Session(start=datetime(2024, 2, 27, 14, 15).timestamp(), span=180, room=1).full_code)
    print(Session(start=datetime(2024, 2, 27, 22, 0).timestamp(), span=240, room=2).full_code)

    print(Session(start=datetime(2024, 2, 28, 11, 45).timestamp(), span=235, room=1).full_code)
    print(Session(start=datetime(2024, 2, 28, 22, 00).timestamp(), span=120, room=0).full_code)

    print(Session(start=datetime(2024, 2, 29, 2, 00).timestamp(), span=120, room=1).full_code)
    print(Session(start=datetime(2024, 2, 29, 4, 00).timestamp(), span=90, room=2).full_code)
    print(Session(start=datetime(2024, 2, 29, 23, 00).timestamp(), span=60, room=0).full_code)

    print(Session(start=datetime(2024, 3, 1, 3, 00).timestamp(), span=120, room=1).full_code)
    print(Session(start=datetime(2024, 3, 1, 6, 30).timestamp(), span=30, room=0).full_code)
    print(Session(start=datetime(2024, 3, 1, 7, 00).timestamp(), span=15, room=0).full_code)
    print(Session(start=datetime(2024, 3, 1, 22, 30).timestamp(), span=90, room=2).full_code)

    print(Session(start=datetime(2024, 3, 2, 6, 0).timestamp(), span=60, room=0).full_code)
    print(Session(start=datetime(2024, 3, 2, 10, 0).timestamp(), span=90, room=1).full_code)
    print(Session(start=datetime(2024, 3, 2, 16, 0).timestamp(), span=120, room=0).full_code)
    print(Session(start=datetime(2024, 3, 2, 21, 0).timestamp(), span=180, room=1).full_code)

    print(Session(start=datetime(2024, 3, 3, 3, 00).timestamp(), span=120, room=0).full_code)
    print(Session(start=datetime(2024, 3, 3, 5, 30).timestamp(), span=60, room=1).full_code)
    print(Session(start=datetime(2024, 3, 3, 7, 00).timestamp(), span=90, room=0).full_code)
    print(Session(start=datetime(2024, 3, 3, 22, 30).timestamp(), span=90, room=2).full_code)
    raise SystemExit

    
    def delete_last_lines(n=1):
        for _ in range(n):
            sys.stdout.write('\033[A')  # Move cursor up one line
            sys.stdout.write('\033[K')  # Clear the line
        sys.stdout.flush()
    
    sess = Session(Timestamp((datetime(2024, 2, 17, 14, 18)).timestamp()), 1, 5)
    print("ORIGINAL")
    print(sess)
    print(repr(sess))
    start = Timestamp(max(datetime.now().timestamp(), datetime.now().timestamp() - sess.time_until()))

    while True:
        print("Time until:", sess.time_until())
        print("Time left:", sess.time_left(start))
        time.sleep(1)
        delete_last_lines(2)
