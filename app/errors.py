from flask import jsonify


MESSAGES = {
    "EMPTY_FILE": "文件为空",
    "BLANK_FILE": "文件只有空白",
    "HEADER_ONLY": "文件只有表头",
    "HEADER_MISMATCH": "表头与本项目字段不一致",
    "UNCLOSED_QUOTE": "引号未闭合，文件已拒收",
    "TOO_MANY_ROWS": "数据行超过上限",
    "FILE_TOO_LARGE": "文件超过大小上限",
    "KEY_MISSING": "主键为空",
    "ORDER_MISSING": "团单号为空",
    "CONFLICT_DUPLICATE": "同一键存在冲突内容",
    "SAMPLE_UNKNOWN": "样例不存在",
    "STAGE_UNKNOWN": "阶段不存在",
    "RUN_NOT_FOUND": "批次不存在",
    "STALE_REVIEW": "批次已被更新，请刷新后复核",
    "GATE_BLOCKED": "存在阻断项，不能签发",
    "NOT_APPROVED": "批次尚未签发",
    "BAD_REQUEST": "请求内容不完整",
    "BAD_DIRECTION": "票款方向不在允许集合内",
    "BAD_CAP": "票款上限不能为负",
    "EVIDENCE_DIRECTION": "逐票凭据方向与票方向不一致",
    "EVIDENCE_OVER_CAP": "逐票凭据超过该票上限",
    "NET_DIRECTION": "净额方向与团单方向冲突",
    "NET_UNBALANCED": "净额在各票方向与上限内无法配平",
    "NET_INCONSISTENT": "同团净额不一致",
    "ORDER_MIX": "同一批次混入多个团单",
    "SIGNED_AMOUNT_MISMATCH": "后补凭据与已签款对不上，余款暂缓",
}


class DomainIssue(Exception):
    def __init__(self, code: str, status: int = 400, detail: str | None = None):
        self.code = code
        self.status = status
        self.detail = detail
        super().__init__(code)


def error_response(exc: DomainIssue):
    return jsonify(error=exc.detail or MESSAGES.get(exc.code, "请求无法处理"), code=exc.code), exc.status
