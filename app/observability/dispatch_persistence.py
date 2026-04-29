from datetime import datetime

def persist_dispatch(dispatch: dict, db):
    record = {
        "event": dispatch.get("event"),
        "execution_depth": dispatch.get("execution_depth"),
        "payload": dispatch,
        "created_at": datetime.utcnow().isoformat()
    }
    try:
        db.add(record)
        db.commit()
    except Exception:
        pass
    return record
