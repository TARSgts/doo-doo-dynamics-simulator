STAGE_LABELS = {
    "queued": "Waiting to start",
    "starting": "Starting job",
    "creating": "Creating geometry",
    "meshing": "Generating mesh",
    "preparing": "Preparing solver input",
    "solving": "CalculiX solving",
    "cfd-solving": "Solving numerical flow model",
    "reading": "Reading solver results",
    "exporting": "Saving results",
    "completed": "Completed",
    "failed": "Failed — see job log",
    "cancelled": "Stopped by user",
}

CONVERGENCE_STEPS = ("meshing", "preparing", "solving", "reading", "exporting")
for _total in range(2, 9):
    for _number in range(1, _total + 1):
        for _step in CONVERGENCE_STEPS:
            STAGE_LABELS[f"convergence-{_number}-{_total}-{_step}"] = f"Mesh {_number} of {_total} · {STAGE_LABELS[_step]}"


def elapsed_label(seconds):
    total = max(0, int(seconds))
    minutes, seconds_part = divmod(total, 60)
    hours, minutes_part = divmod(minutes, 60)
    return f"{hours}:{minutes_part:02d}:{seconds_part:02d}" if hours else f"{minutes_part:02d}:{seconds_part:02d}"
