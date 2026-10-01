# -*- coding: utf-8 -*-
"""屏幕截取：mss 抓取主显示器（物理像素）"""
import mss
import numpy as np


class ScreenCapturer:
    def __init__(self):
        self._mss = mss.mss()
        self._monitor = self._mss.monitors[1]

    def grab(self):
        """返回 BGR 格式 numpy 数组"""
        image = self._mss.grab(self._monitor)
        return np.asarray(image)[:, :, :3]

    def close(self):
        self._mss.close()
