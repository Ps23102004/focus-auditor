"""Tiny fake TV: screens are uiautomator XML, navigation is a dict. No adb, no device."""
from fa.tree import parse


def node(cls="android.widget.Button", bounds=(0, 0, 100, 100), text="", desc="", focusable=True, focused=False,
         clickable=True, children=()):
    b = "[%d,%d][%d,%d]" % bounds
    return (f'<node class="{cls}" text="{text}" content-desc="{desc}" focusable="{str(focusable).lower()}" '
            f'focused="{str(focused).lower()}" clickable="{str(clickable).lower()}" bounds="{b}" package="a.b.c">'
            + "".join(children) + "</node>")


def screen(*kids):
    return '<hierarchy rotation="0">' + node("android.widget.FrameLayout", (0, 0, 1920, 1080), focusable=False,
                                              clickable=False, children=kids) + "</hierarchy>"


class FakeDev:
    def __init__(self, screens, nav, start="s0"):
        self.screens, self.nav, self.start, self.state, self.presses = screens, nav, start, start, []

    def cold_start(self):
        self.state, self.presses = self.start, []

    def press(self, key):
        self.presses.append(key)
        self.state = self.nav.get((self.state, key), self.state)

    def read(self):
        return parse(self.screens[self.state])
