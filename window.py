# -*- coding: utf-8 -*-
"""窗口工具：按标题子串激活游戏窗口（config.window.title 为空则跳过）
另提供提权检查：游戏以管理员运行而本脚本未提权时，UIPI 会拦截所有点击注入。
"""
import ctypes
import os
from ctypes import wintypes

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_advapi32 = ctypes.windll.advapi32


def focus_game_window(title):
    if not title:
        return True
    hwnd = find_window(title)
    if not hwnd:
        return False
    _user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    return bool(_user32.SetForegroundWindow(hwnd))


def find_window(title_substring):
    """按标题子串查找首个可见窗口，找不到返回 None"""
    if not title_substring:
        return None
    matches = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum_proc(hwnd, _lparam):
        if not _user32.IsWindowVisible(hwnd):
            return True
        length = _user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        _user32.GetWindowTextW(hwnd, buffer, length + 1)
        if title_substring.lower() in buffer.value.lower():
            matches.append(hwnd)
            return False
        return True

    _user32.EnumWindows(_enum_proc, 0)
    return matches[0] if matches else None


def is_process_elevated(pid):
    """查询进程是否以管理员（提权）运行；查询失败返回 None"""
    if not pid:
        return None
    handle = _kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        token = wintypes.HANDLE()
        if not _advapi32.OpenProcessToken(handle, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
            return None
        try:
            elevated = wintypes.DWORD()
            length = wintypes.DWORD()
            ok = _advapi32.GetTokenInformation(token, 20, ctypes.byref(elevated),  # TokenElevation
                                               ctypes.sizeof(elevated), ctypes.byref(length))
            return bool(elevated.value) if ok else None
        finally:
            _kernel32.CloseHandle(token)
    finally:
        _kernel32.CloseHandle(handle)


def elevation_error(game_title):
    """游戏提权而本脚本未提权时返回致命错误文案，否则返回 None

    UIPI 会把未提权进程的 SendInput/按键全部拦截（表现为鼠标完全不动），
    必须让两者处于同一完整性级别。
    """
    if not game_title:
        game_title = "异环"
    hwnd = find_window(game_title)
    if not hwnd:
        return None  # 游戏未开：交给后续流程处理
    pid = wintypes.DWORD()
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    game_elevated = is_process_elevated(pid.value)
    self_elevated = is_process_elevated(os.getpid())
    if game_elevated and self_elevated is False:
        return (f"游戏以管理员运行（PID {pid.value}），本脚本未提权 → UIPI 拦截点击，"
                f"鼠标不会动。请用 run_as_admin.bat 启动，或右键以管理员身份运行 PyCharm")
    return None
