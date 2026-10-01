# -*- coding: utf-8 -*-
"""全局状态：界面阶段/回合/估价/高价标记"""


class State:
    def __init__(self):
        # boot=启动等待 | awaiting=等待进入竞拍 | playing=竞拍中 | cooldown=结算后冷却
        self.phase = "boot"
        self.cycle = 1            # 当前是第几局
        self.current_round = None  # 本局已处理到的回合（None=未开始）
        self.estimate = None       # 最近一次读到的估价
        self.high_i = None         # 估价>500万触发的回合，本局永久生效
        self.instrument_used = False
        self.bid_bonus = 0       # 本局累计随机加价（每轮 +randint(min,max)*10000）
        self.match_started_at = None
        self.entry_failures = 0
        self.cooldown_until = 0.0

    def reset_game(self):
        """新一局开始：清空本局数据"""
        self.current_round = None
        self.estimate = None
        self.high_i = None
        self.instrument_used = False
        self.bid_bonus = 0
