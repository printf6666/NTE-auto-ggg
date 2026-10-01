# -*- coding: utf-8 -*-
"""场景流程：启动 → 竞拍回合 → 结算 → 循环下一局

阶段状态机（state.phase）：
  boot      脚本启动，等待 startup_wait 后点开始匹配（首局不购买道具）
  awaiting  等 OCR 识别到「竞拍第N回合」（超时重试点开始匹配，超过次数致命退出）
  playing   竞拍中：检测跳过（结算）与回合变化，回合变化触发当回合动作
  cooldown  结算完成，等待 cooldown_wait 后购买道具（第2局起）→ 开始匹配
"""
import logging
import random
import re
import time

import bid as bid_mod

log = logging.getLogger("yihuan")

_ROUND_RE = re.compile(r"第\s*([0-9])")
_ESTIMATE_RE = re.compile(r"[^0-9]")


def parse_round(text):
    """从「竞拍第N回合」提取回合数，容忍 OCR 断字/多字"""
    match = _ROUND_RE.search(text or "")
    return int(match.group(1)) if match else None


def parse_estimate(text):
    """估价区域文本 → 整数（去除千分位逗号等非数字字符）"""
    digits = _ESTIMATE_RE.sub("", text or "")
    if not digits or len(digits) > 9:
        return None
    return int(digits)


class Flow:
    def __init__(self, config, state, ocr, runner, capturer):
        self.config = config
        self.state = state
        self.ocr = ocr
        self.runner = runner
        self.capturer = capturer
        self.regions = config["regions"]
        self.actions = config["actions"]
        self.loop = config["loop"]
        self.bid_config = config["bid"]

    # ---------- OCR 辅助 ----------
    def read_round(self, image):
        return self.ocr.read(image, self.regions["round"])

    def skip_appeared(self, image=None):
        if image is None:
            image = self.capturer.grab()
        return "跳过" in self.ocr.read(image, self.regions["skip"])

    def read_estimate(self):
        times = int(self.loop.get("estimate_retry_times", 5))
        delay = float(self.loop.get("estimate_retry_delay", 1.0))
        for attempt in range(1, times + 1):
            image = self.capturer.grab()
            text = self.ocr.read(image, self.regions["estimate"])
            value = parse_estimate(text)
            if value is not None:
                log.info("[估价] 识别 %r → %d（第 %d/%d 次）", text, value, attempt, times)
                return value
            log.info("[估价] 识别失败 %r（第 %d/%d 次）", text, attempt, times)
            if attempt < times:
                time.sleep(delay)
        return None

    # ---------- 主入口 ----------
    def tick(self, image):
        phase = self.state.phase
        if phase == "boot":
            self.on_boot()
        elif phase == "awaiting":
            self.on_awaiting(image)
        elif phase == "playing":
            self.on_playing(image)
        elif phase == "cooldown":
            self.on_cooldown()

    # ---------- 启动 ----------
    def on_boot(self):
        wait = float(self.loop.get("startup_wait", 10.0))
        log.info("[启动] 等待 %.0f 秒后点开始匹配（首局不购买道具）", wait)
        self.runner.wait(wait, "启动")
        self.start_match()
        self.state.phase = "awaiting"
        self.state.match_started_at = time.time()

    def start_match(self):
        steps = self.actions.get("开始匹配")
        if not steps:
            self.runner.fail("config.actions.开始匹配 坐标缺失")
        self.runner.run("开始匹配", steps)

    # ---------- 等待进入竞拍 ----------
    def on_awaiting(self, image):
        state = self.state
        timeout = float(self.loop.get("auction_entry_timeout", 120.0))
        if state.match_started_at and time.time() - state.match_started_at > timeout:
            state.entry_failures += 1
            max_retries = int(self.loop.get("auction_entry_retries", 3))
            if state.entry_failures > max_retries:
                self.runner.fail(f"开始匹配后 {timeout:.0f} 秒未识别到竞拍回合，重试 {max_retries} 次仍失败")
            log.info("[等待竞拍] 超时，重试点开始匹配（%d/%d）", state.entry_failures, max_retries)
            self.start_match()
            state.match_started_at = time.time()
            return
        round_number = parse_round(self.read_round(image))
        if round_number is None:
            return
        state.phase = "playing"
        if round_number != 1:
            log.info("[竞拍] 未识别到第1回合，从第 %d 回合开始处理", round_number)
        self.handle_round(round_number)

    # ---------- 竞拍中 ----------
    def on_playing(self, image):
        state = self.state
        if state.current_round is not None and self.skip_appeared(image):
            self.settlement()
            return
        round_number = parse_round(self.read_round(image))
        if round_number is None:
            return
        current = state.current_round
        if current is None:
            self.handle_round(round_number)
            return
        if round_number == current:
            return
        if round_number < current:
            return  # 回合文本回退：忽略（疑似误识别）
        if round_number > current + 1:
            log.info("[竞拍] 回合跳变 %d → %d，中间回合已跳过", current, round_number)
        self.handle_round(round_number)

    # ---------- 回合动作 ----------
    def handle_round(self, round_number):
        state = self.state
        state.current_round = round_number
        wait = float(self.loop.get("round_wait", 10.0))
        log.info("[回合] 第 %d 回合开始，等待 %.0f 秒", round_number, wait)
        self.runner.wait(wait, f"第{round_number}回合")
        if self.skip_appeared():  # 等待期间有人秒掉
            self.settlement()
            return
        # 使用超级鉴定仪器（第一回合；若漏识别第1回合则在首个识别到的回合补用）
        if not state.instrument_used:
            steps = self.actions.get("使用仪器")
            if not steps:
                self.runner.fail("config.actions.使用仪器 坐标缺失")
            log.info("[回合] 使用超级鉴定仪器")
            self.runner.run("使用仪器", steps)
            state.instrument_used = True
            self.runner.wait(float(self.loop.get("item_wait", 10.0)), "使用仪器后")
            if self.skip_appeared():
                self.settlement()
                return
        # 第1/3回合读取当前估价
        if round_number in (1, 3):
            value = self.read_estimate()
            if value is not None:
                state.estimate = value
                threshold = int(self.bid_config.get("high_threshold", 5000000))
                if value > threshold and state.high_i is None:
                    state.high_i = round_number
                    log.info("[高价] 第 %d 回合估价 %d > %d，高价公式本局永久生效",
                             round_number, value, threshold)
        bid_value = self.compute_bid(round_number)
        if bid_value is None:
            log.info("[出价] 第 %d 回合无有效估价，本回合不出价", round_number)
            return
        self.submit_bid(round_number, bid_value)

    def compute_bid(self, round_number):
        state = self.state
        if state.high_i is not None:
            return bid_mod.compute_bid(round_number, None, state.high_i, self.bid_config)
        estimate = state.estimate
        if estimate is None:
            fake = int(self.bid_config.get("fake_estimate", 0) or 0)
            if fake > 0:
                log.info("[出价] 估价缺失，使用 fake_estimate=%d 验证公式", fake)
                estimate = fake
            else:
                return None
        # 估价≤500万：每轮加价随机 bonus_wan_min~max 万，累计入 bid_bonus（防止固定加价被看穿）
        lo = int(self.bid_config.get("bonus_wan_min", 1))
        hi = int(self.bid_config.get("bonus_wan_max", 5))
        increment = random.randint(lo, hi) * 10000
        state.bid_bonus += increment
        log.info("[出价] 本轮随机加价 %d 万，累计加价 %d（估价 %d）",
                 increment // 10000, state.bid_bonus // 10000, estimate)
        return bid_mod.compute_bid(round_number, estimate, None, self.bid_config,
                                   bonus=state.bid_bonus)

    def submit_bid(self, round_number, bid_value):
        digits = bid_mod.bid_digits(bid_value)
        log.info("[出价] 第 %d 回合 出价 %d → 输入 %s 万", round_number, bid_value, digits)
        steps = list(self.actions.get("出价") or [])
        if not steps:
            self.runner.fail("config.actions.出价 坐标缺失")
        for digit in digits:
            group = self.actions.get(f"数字{digit}")
            if not group:
                self.runner.fail(f"config.actions.数字{digit} 坐标缺失")
            steps.extend(group)
        if not self.actions.get("数字万"):
            self.runner.fail("config.actions.数字万 坐标缺失")
        steps.extend(self.actions["数字万"])
        if not self.actions.get("确认出价"):
            self.runner.fail("config.actions.确认出价 坐标缺失")
        steps.extend(self.actions["确认出价"])
        # 出价超过阈值（不含等于）时游戏弹「本次出价过高是否继续」二次确认
        threshold = int(self.bid_config.get("confirm_popup_threshold", 2000000))
        if bid_value > threshold:
            popup_steps = self.actions.get("出价过高继续")
            if not popup_steps:
                self.runner.fail("config.actions.出价过高继续 坐标缺失")
            log.info("[出价] %d > %d，弹二次确认，点继续", bid_value, threshold)
            steps.extend(popup_steps)
        self.runner.run(f"第{round_number}回合出价", steps)

    # ---------- 结算 ----------
    def settlement(self):
        state = self.state
        settle_wait = float(self.loop.get("settle_wait", 3.0))
        sell_wait = float(self.loop.get("sell_wait", 2.0))
        log.info("[结算] 竞拍结束（第 %d 局）", state.cycle)
        skip_steps = list(self.actions.get("跳过") or [])
        if not skip_steps:
            self.runner.fail("config.actions.跳过 坐标缺失")
        skip_steps.append({"wait": settle_wait})
        self.runner.run("结算-跳过", skip_steps)
        # 结算画面读最终估价（文本框位置/格式与回合中相同）
        threshold = int(self.bid_config.get("high_threshold", 5000000))
        final_estimate = self.read_estimate()
        if final_estimate is not None:
            over_high = final_estimate > threshold
            log.info("[结算] 最终估价 %d，阈值 %d → %s",
                     final_estimate, threshold, "超500万" if over_high else "未超500万")
        else:
            over_high = state.high_i is not None
            log.info("[结算] 最终估价识别失败，回退本局 high_i=%s → %s",
                     state.high_i, "超500万" if over_high else "未超500万")
        steps = []
        if not over_high:
            # 最终估价≤500万：出售前先点红色按键(2448,1156)
            red_steps = self.actions.get("出售红色按键")
            if not red_steps:
                self.runner.fail("config.actions.出售红色按键 坐标缺失")
            steps.extend(red_steps)
        # 两种情况都点两下出售：第一下触发出售，隔 sell_wait 第二下关闭「获得xxx金币」弹窗
        sell_steps = self.actions.get("一键出售")
        if not sell_steps:
            self.runner.fail("config.actions.一键出售 坐标缺失")
        steps.extend(sell_steps)
        steps.append({"wait": sell_wait})
        sell_pos = [s for s in sell_steps if isinstance(s, list)]
        if not sell_pos:
            self.runner.fail("config.actions.一键出售 坐标缺失")
        steps.append(list(sell_pos[0]))
        steps.append({"wait": 0.5})
        exit_steps = self.actions.get("退出")
        if not exit_steps:
            self.runner.fail("config.actions.退出 坐标缺失")
        steps.extend(exit_steps)
        self.runner.run("结算-出售", steps)
        state.reset_game()
        state.cycle += 1
        cooldown_wait = float(self.loop.get("cooldown_wait", 10.0))
        state.phase = "cooldown"
        state.cooldown_until = time.time() + cooldown_wait
        log.info("[结算] 完成，等待 %.0f 秒后进入下一局", cooldown_wait)

    def on_cooldown(self):
        if time.time() < self.state.cooldown_until:
            return
        # 第2局起每局先补道具（首局在 boot 阶段直接匹配）
        buy_steps = self.actions.get("购买道具")
        if not buy_steps:
            self.runner.fail("config.actions.购买道具 坐标缺失")
        log.info("[主界面] 购买道具")
        self.runner.run("购买道具", buy_steps)
        self.state.entry_failures = 0
        self.start_match()
        self.state.phase = "awaiting"
        self.state.match_started_at = time.time()
