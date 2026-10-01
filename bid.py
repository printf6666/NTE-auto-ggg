# -*- coding: utf-8 -*-
"""出价计算：常规公式 / 高价公式 / 向上取整到万"""


def ceil_to_wan(value):
    return -(-value // 10000) * 10000


def compute_bid(round_number, estimate, high_i, bid_config, bonus=None):
    """计算回合出价（已向上取整到万）。

    high_i 非空（本局任一回合估价>500万后永久生效）:
        8888888 + 3333333 * (回合数 - high_i)
    否则:
        估价 * 1.3 + bonus
    bonus=None 时回退 base_per_round * 回合数（自测/兼容）；
    正常流程由 scenes 传入本局累计随机加价 bonus_wan_min~max 万/轮。
    """
    if high_i is not None:
        raw = bid_config["high_base"] + bid_config["high_step"] * (round_number - high_i)
    else:
        multiplier = float(bid_config.get("multiplier", 1.5))
        if bonus is None:
            bonus = int(bid_config.get("base_per_round", 30997)) * round_number
        raw = int(estimate * multiplier) + int(bonus)
    return int(ceil_to_wan(raw))


def bid_digits(bid_value):
    """取整到万后的输入序列，如 1540000 → '154'（配合数字万键）"""
    return str(bid_value // 10000)


if __name__ == "__main__":
    cfg = {"multiplier": 1.3, "base_per_round": 30997,
           "high_base": 8888888, "high_step": 3333333}
    checks = [
        ((1, 1000000, None), 1340000, "134"),
        ((2, 1500000, None), 2020000, "202"),
        ((3, 4000000, None), 5300000, "530"),
        ((1, None, 1), 8890000, "889"),
        ((2, None, 1), 12230000, "1223"),
        ((5, None, 1), 22230000, "2223"),
        ((3, None, 3), 8890000, "889"),
    ]
    for (r, est, hi), expected, digits in checks:
        got = compute_bid(r, est, hi, cfg)
        assert got == expected, f"round={r} est={est} high_i={hi}: got {got}, want {expected}"
        if digits:
            assert bid_digits(got) == digits, f"digits {bid_digits(got)} != {digits}"
    # 含0的输入序列: high_i=1 第2回合 12222221 → 12230000 → '1223'
    assert bid_digits(compute_bid(2, None, 1, cfg)) == "1223"
    print("bid self-test OK")
