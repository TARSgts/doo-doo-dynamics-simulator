STAGE_LABELS = {
    "queued": "Waiting to start",
    "starting": "Starting job",
    "creating": "Creating geometry",
    "meshing": "Generating mesh",
    "preparing": "Preparing solver input",
    "solving": "CalculiX solving",
    "reading": "Reading solver results",
    "exporting": "Saving results",
    "completed": "Completed",
    "failed": "Failed — see job log",
}


def elapsed_label(seconds):
    total = max(0, int(seconds))
    minutes, seconds_part = divmod(total, 60)
    hours, minutes_part = divmod(minutes, 60)
    return f"{hours}:{minutes_part:02d}:{seconds_part:02d}" if hours else f"{minutes_part:02d}:{seconds_part:02d}"
