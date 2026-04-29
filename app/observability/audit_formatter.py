def format_audit(dispatch):
    return {
        "event": dispatch.get("event"),
        "summary": dispatch.get("summary"),
        "receipts": dispatch.get("receipts"),
        "reports": dispatch.get("reports")
    }

