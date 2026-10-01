# -*- coding: utf-8 -*-
"""异环自动竞拍 主循环：截屏 → 按阶段场景检测 → 执行动作组

正常运行完全静默（仅致命错误打印一行）；
debug.dry_run / debug.step 打开时输出识别与动作日志。
"""
import json
import logging
import os
import sys
import time

from actions import ActionRunner
from mouse import Mouse
from ocr import OCREngine
from scenes import Flow
from screen import ScreenCapturer
from state import State
from window import elevation_error


def setup_dpi():
    """进程 DPI 感知：保证截屏与鼠标坐标均为物理像素"""
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def setup_stdio():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def setup_logging(config):
    debug = config.get("debug", {})
    level = logging.INFO if (debug.get("dry_run") or debug.get("step")) else logging.ERROR
    logging.basicConfig(level=level, format="[%(asctime)s] %(levelname)s %(message)s",
                        datefmt="%H:%M:%S", stream=sys.stdout, force=True)
    logging.getLogger("RapidOCR").setLevel(logging.ERROR)


def main():
    setup_stdio()
    setup_dpi()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base_dir, "config.json"), encoding="utf-8-sig") as file:
            config = json.load(file)
    except Exception as error:
        print(f"[致命] 读取 config.json 失败: {error}")
        return 1
    setup_logging(config)
    error = elevation_error(config.get("window", {}).get("title") or "异环")
    if error:
        print(f"[致命] {error}")
        return 1
    try:
        ocr_engine = OCREngine(config)
    except Exception as error:
        print(f"[致命] OCR 引擎加载失败: {error}")
        return 1

    state = State()
    mouse = Mouse(config)
    runner = ActionRunner(config, mouse)
    capturer = ScreenCapturer()
    flow = Flow(config, state, ocr_engine, runner, capturer)
    mode = "空跑" if runner.dry_run else "步进" if runner.step else "自动"
    logging.getLogger("yihuan").info("异环自动竞拍已启动，模式: %s", mode)

    try:
        while True:
            start = time.monotonic()
            image = capturer.grab()
            flow.tick(image)
            elapsed = time.monotonic() - start
            interval = float(config["loop"].get("interval", 1.0))
            if elapsed < interval:
                time.sleep(interval - elapsed)
    except KeyboardInterrupt:
        pass
    except SystemExit as exit_info:
        capturer.close()
        return int(exit_info.code) if isinstance(exit_info.code, int) else 1
    capturer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
