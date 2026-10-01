# -*- coding: utf-8 -*-
"""动作执行：点击 / 等待 / 按键

- 正常模式：顺序执行
- debug.dry_run：只打印不点击、跳过等待（快速验证出价公式）
- debug.step：每个点击前按回车执行（验证点击顺序，等待仍按真实时间）
坐标语义见 config._说明：动作组内 [x,y] 为点击中心点，{"wait": 秒} 为等待。
"""
import logging
import time

from window import elevation_error, focus_game_window

log = logging.getLogger("yihuan")


def describe(item):
    if isinstance(item, dict):
        if "wait" in item:
            return f"等待 {item['wait']} 秒"
        if "key" in item:
            return f"按键 {item['key']}"
    return f"点击 ({item[0]}, {item[1]})"


class ActionRunner:
    def __init__(self, config, mouse):
        self.config = config
        self.mouse = mouse
        self.dry_run = bool(config.get("debug", {}).get("dry_run", False))
        self.step = bool(config.get("debug", {}).get("step", False))
        self.action_gap = float(config["loop"].get("action_gap", 0.5))
        self.window_title = config.get("window", {}).get("title", "")

    def wait(self, seconds, reason=""):
        """场景级等待：dry_run 跳过，其余按真实时间睡"""
        seconds = float(seconds)
        if seconds <= 0:
            return
        if self.dry_run:
            log.info("[空跑] 跳过等待 %.1f 秒 %s", seconds, reason)
            return
        time.sleep(seconds)

    def run(self, group_name, steps):
        """执行一个动作序列（点击/等待/按键混合）"""
        if not steps:
            log.error("动作组「%s」为空", group_name)
            return
        if not self.dry_run:
            error = elevation_error(self.window_title or "异环")
            if error:
                self.fail(error)
        focus_game_window(self.window_title)
        for item in steps:
            desc = describe(item)
            if self.dry_run:
                log.info("[空跑] %s: %s", group_name, desc)
                continue
            if self.step and not isinstance(item, dict):
                try:
                    input(f"[步进] {group_name} | Enter 执行 {desc} > ")
                except EOFError:
                    self.step = False  # 非交互环境退化为自动执行
            self._execute_one(item)

    def _execute_one(self, item):
        if isinstance(item, dict):
            if "wait" in item:
                time.sleep(float(item["wait"]))
            elif "key" in item:
                self.mouse.press_key(item["key"])
                time.sleep(self.action_gap)
            return
        self.mouse.click(item[0], item[1])
        time.sleep(self.action_gap)

    def fail(self, message):
        """致命错误：打印一行并退出"""
        log.error(message)
        raise SystemExit(1)
