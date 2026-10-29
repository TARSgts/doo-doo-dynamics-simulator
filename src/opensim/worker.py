import argparse
import os
from pathlib import Path
import threading
import time
import traceback


from opensim.solver import cancel_active_solvers
from opensim.workspace import Workspace

CANCEL_POLL_SECONDS = 0.3
CANCELLED_EXIT_CODE = 3


def watch_for_cancel(workspace: Workspace, job_id: str, stop: threading.Event, exit_process=os._exit):
    """Poll the shared workspace; when the job is stopped, end CalculiX and this worker.

    Meshing runs inside Gmsh's native code and cannot be interrupted politely,
    so the worker process exits immediately instead of waiting for it.
    """
    while not stop.wait(CANCEL_POLL_SECONDS):
        try:
            status = workspace.get_job(job_id)["status"]
        except Exception:
            continue  # A briefly locked database must not kill a healthy job.
        if status == "cancelled":
            killed = cancel_active_solvers()
            print(f"Stop requested; ended {killed} solver process(es) and exiting worker.", flush=True)
            exit_process(CANCELLED_EXIT_CODE)
            return


def execute(workspace: Workspace, job_id: str):
    job = workspace.get_job(job_id)
    directory = workspace.job_directory(job_id)
    parameters = job["payload"]["parameters"]
    with workspace.connect() as connection:
        started = connection.execute("UPDATE jobs SET status='running',updated=? WHERE id=? AND status='queued'",
                                     (time.time(), job_id)).rowcount
    if not started:
        print("Job was stopped before the worker started.", flush=True)
        return
    stop_watching = threading.Event()
    threading.Thread(target=watch_for_cancel, args=(workspace, job_id, stop_watching), daemon=True).start()
    try:
        def progress(stage):
            workspace.set_job_progress(job_id, stage)
        progress("starting")
        from opensim.execution.dispatch import run_job
        result = run_job(workspace, job, directory, progress)
        if result is None:
            return
        workspace.finish_job(job_id, result=result)
    except Exception as error:
        traceback.print_exc()
        workspace.finish_job(job_id, error=str(error))
    finally:
        stop_watching.set()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--job", required=True)
    arguments = parser.parse_args()
    execute(Workspace(arguments.workspace), arguments.job)


if __name__ == "__main__":
    main()
