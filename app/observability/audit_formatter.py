def format_executive_output(dispatch: dict):
    return {
        "executive_summary": dispatch.get("executive_diagnostic"),
        "main_risk": dispatch.get("main_risk"),
        "recommended_actions": dispatch.get("recommended_actions"),
        "status": dispatch.get("event"),
        "execution_depth": dispatch.get("execution_depth")
    }

def extract_dispatch_receipts(dispatch: dict):
    return dispatch.get("dispatch_receipts", [])

def extract_specialist_reports(dispatch: dict):
    return dispatch.get("specialist_reports", [])
