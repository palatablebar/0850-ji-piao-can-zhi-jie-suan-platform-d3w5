"""团单净额拆票求解器。

场景：航司只给一个净额 N（退款与改期补收轧差后的有符号金额）。每张票有自己的
方向（REFUND / CHARGE）和上限 cap，票 i 的应结金额 x_i 满足::

    REFUND: -cap_i <= x_i <= 0      （贡献 |x_i| 记为非负整数）
    CHARGE:  0    <= x_i <= cap_i

且 sum(x_i) == N。

缺逐票凭据的票不能凭空指定金额，只有当**所有**满足方向、上限与净额的拆法里，
该票的应结金额都取同一个值时，才允许签这张票。

每张票对"非负贡献和"的贡献都是连续整数区间 [0, cap_i]，连续整数区间做逐票
Minkowski 和仍然是连续区间，因此全部票、以及去掉任意一张票后的可行贡献和集合
都是连续整数区间，前缀/后缀 DP 即可在 O(n) 内求出每张票贡献值的可行范围。
"""
from dataclasses import dataclass


@dataclass
class TicketClaim:
    index: int
    ticket_id: str
    direction: str  # REFUND / CHARGE
    cap: int        # 非负整数（分）
    has_evidence: bool
    evidence: int   # 有符号凭据金额；无凭据时为 0


@dataclass
class SplitResult:
    feasible: bool
    target: int                     # 变量票需要凑出的非负贡献和
    ranges: list                    # 每张变量票 (low, high) 含端点
    reason: str = ""


def _intervals(tickets):
    return [(0, t.cap) for t in tickets]


def _prefix_reach(intervals):
    """prefix[k] = 仅前 k 张票（0..k-1）可凑出的贡献和闭区间。"""
    prefix = [(0, 0)]
    low = high = 0
    for lo, hi in intervals:
        low += lo
        high += hi
        prefix.append((low, high))
    return prefix


def _suffix_reach(intervals):
    """suffix[k] = 仅票 k..n-1 可凑出的贡献和闭区间。"""
    n = len(intervals)
    suffix = [(0, 0)] * (n + 1)
    suffix[n] = (0, 0)
    low = high = 0
    for k in range(n - 1, -1, -1):
        lo, hi = intervals[k]
        low += lo
        high += hi
        suffix[k] = (low, high)
    return suffix


def split_net(tickets, net_total):
    """在方向与上限内分解净额，返回每张**缺凭据**票的可行贡献区间。

    已有逐票凭据的票先从净额中扣除；剩余净额必须只由缺凭据票凑出。
    """
    fixed = 0
    variables = []
    for ticket in tickets:
        if ticket.has_evidence:
            fixed += ticket.evidence
        else:
            variables.append(ticket)
    # 剩余有符号净额；转成变量票的非负贡献目标
    residual_signed = net_total - fixed
    target = -residual_signed
    if not variables:
        return SplitResult(feasible=(residual_signed == 0), target=target,
                           ranges=[], reason="NET_UNBALANCED" if residual_signed else "EVIDENCE_COMPLETE")

    intervals = _intervals(variables)
    prefix = _prefix_reach(intervals)
    suffix = _suffix_reach(intervals)
    total_lo, total_hi = prefix[-1]
    if not (total_lo <= target <= total_hi):
        return SplitResult(False, target, [(0, t.cap) for t in variables], "NET_UNBALANCED")

    ranges = []
    for k, ticket in enumerate(variables):
        cap = ticket.cap
        # 票 k 取贡献 c 时，其余票需凑 target - c
        pre_lo, pre_hi = prefix[k]
        suf_lo, suf_hi = suffix[k + 1]
        rest_lo, rest_hi = pre_lo + suf_lo, pre_hi + suf_hi
        # c 可行 <=> rest_lo <= target - c <= rest_hi
        low = max(0, target - rest_hi)
        high = min(cap, target - rest_lo)
        if low > high:  # 理论上不会发生（整体可行），防御性处理
            return SplitResult(False, target, [], "NET_UNBALANCED")
        ranges.append((low, high))
    return SplitResult(True, target, ranges, "UNIQUE_OR_AMBIGUOUS")
