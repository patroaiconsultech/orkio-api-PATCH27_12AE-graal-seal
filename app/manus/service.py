from app.models import DecisionHistory

def approve_task(task, actor_email, db):
    if task.status != "founder_approval":
        raise Exception("Invalid state")

    decision = DecisionHistory(
        task_id=task.id,
        actor=actor_email,
        decision="approved"
    )
    db.add(decision)

    task.status = "approved"
    db.commit()

    return task
