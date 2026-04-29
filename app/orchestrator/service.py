from app.models import ExecutionJob
from app.config.runtime import RUNTIME_FLAGS

def create_execution_job(task_id, db):
    if not RUNTIME_FLAGS["allow_write_actions"]:
        raise Exception("Write disabled")

    job = ExecutionJob(
        task_id=task_id,
        status="running"
    )
    db.add(job)
    db.commit()
    return job


def complete_execution(job, db):
    job.status = "completed"
    db.commit()
    return job
