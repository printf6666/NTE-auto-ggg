# -*- coding: utf-8 -*-
"""鼠标/键盘模拟：Win32 SendInput 实现曲线移动与点击"""
import ctypes
import time

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002

KEY_VIRTUAL_CODES = {"esc": 0x1B, "enter": 0x0D, "space": 0x20, "tab": 0x09}

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                ("dwExtraInfo", ULONG_PTR)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", INPUTUNION)]


_user32 = ctypes.windll.user32
_user32.SendInput.argtypes = [ctypes.c_uint, ctypes.POINTER(INPUT), ctypes.c_int]
_user32.SendInput.restype = ctypes.c_uint


def send_input(event):
    _user32.SendInput(1, ctypes.byref(event), ctypes.sizeof(INPUT))


class Mouse:
    def __init__(self, config):
        mouse_config = config["mouse"] if "mouse" in config else {}
        self.move_duration = mouse_config.get("move_duration", 0.4)
        self.start_offset = mouse_config.get("start_offset", [0, 100])
        self.ease_power = mouse_config.get("ease_power", 2.0)
        self.move_interval = mouse_config.get("move_interval", 0.01)
        self.click_hold = mouse_config.get("click_hold", 0.2)
        self.click_wait = mouse_config.get("click_wait", 0.2)
        self.screen_width = config["screen"]["width"]
        self.screen_height = config["screen"]["height"]

    def _move_event(self, target_x, target_y):
        normalized_x = max(0, min(65535, int(target_x * 65535 / max(self.screen_width - 1, 1))))
        normalized_y = max(0, min(65535, int(target_y * 65535 / max(self.screen_height - 1, 1))))
        event = INPUT(type=INPUT_MOUSE)
        event.u.mi = MOUSEINPUT(normalized_x, normalized_y, 0,
                                MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, 0)
        send_input(event)

    def _relative_move_event(self, offset_x, offset_y):
        event = INPUT(type=INPUT_MOUSE)
        event.u.mi = MOUSEINPUT(offset_x, offset_y, 0, MOUSEEVENTF_MOVE, 0, 0)
        send_input(event)

    def _button_event(self, flags):
        event = INPUT(type=INPUT_MOUSE)
        event.u.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
        send_input(event)

    def move_quadratic(self, target_x, target_y):
        start_x = target_x + self.start_offset[0]
        start_y = target_y + self.start_offset[1]
        step_count = max(int(self.move_duration / self.move_interval), 1)
        for step in range(1, step_count + 1):
            progress = step / step_count
            eased = progress ** self.ease_power
            x = start_x + (target_x - start_x) * eased
            y = start_y + (target_y - start_y) * eased
            self._move_event(x, y)
            time.sleep(self.move_interval)

    def click(self, target_x, target_y):
        self.move_quadratic(target_x, target_y)
        self._relative_move_event(2, 0)
        self._relative_move_event(-2, 0)
        time.sleep(self.click_wait)
        self._button_event(MOUSEEVENTF_LEFTDOWN)
        time.sleep(self.click_hold)
        self._button_event(MOUSEEVENTF_LEFTUP)
        self._relative_move_event(1, 0)

    def press_key(self, key_name):
        virtual_code = KEY_VIRTUAL_CODES.get(str(key_name).lower())
        if virtual_code is None:
            return
        down = INPUT(type=INPUT_KEYBOARD)
        down.u.ki = KEYBDINPUT(virtual_code, 0, 0, 0, 0)
        send_input(down)
        time.sleep(0.05)
        up = INPUT(type=INPUT_KEYBOARD)
        up.u.ki = KEYBDINPUT(virtual_code, 0, KEYEVENTF_KEYUP, 0, 0)
        send_input(up)
