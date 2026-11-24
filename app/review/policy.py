def approval_allowed(payload):
    """签发要求阻断项为零；待人工复核的票保留在批次内但不阻断整单签发。"""
    return int(payload["summary"].get("REJECT", 0)) == 0
