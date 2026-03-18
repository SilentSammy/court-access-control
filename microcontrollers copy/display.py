from machine import Timer
import utime

class Display:
    def __init__(self, write_func):
        self.write_func = write_func
        self.texts = {}
        self.timers = {}
        self.blink_timers = {}

    def write(self, message):
        #print(message)
        self.write_func(message)

    def clear(self, priority=None, write=True):
        text_cleared = False
        for p in self.texts.keys() if priority is None else [priority]:
            # clear the text
            text_cleared = self.texts.pop(p, None) is not None or text_cleared

            # clear the previous timers
            self.timers.setdefault(p, Timer()).deinit()
        
        if write and text_cleared:
            self.write(self.get_highest_priority_text())

    def overwrite(self, text, priority=0, duration=-1):
        # set the text
        self.texts[priority] = text

        # if the given text is the highest priority, write it
        if priority == max(self.texts.keys()):
            self.write(text)

        def clear(timer):
            #print("Clearing", priority)
            self.clear(priority)
        
        # clear the previous timer
        self.timers.setdefault(priority, Timer()).deinit()
        if duration > 0:
            # reset the previous timer for this priority
            self.timers[priority].init(period=duration * 1000, mode=Timer.ONE_SHOT, callback=clear)

    def get_highest_priority_text(self):
        if len(self.texts) == 0:
            return ""
        return self.texts[max(self.texts.keys())]
