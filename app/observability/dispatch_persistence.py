from app.models import DispatchRecord

def persist_dispatch(dispatch, db):
    record = DispatchRecord(
        event=dispatch.get("event"),
        payload=dispatch
    )
    db.add(record)
    db.commit()
    return record
