"""Job lifecycle values shared by repository and worker."""
ACTIVE_STATUSES=("queued","running")
TERMINAL_STATUSES={"completed","failed","cancelled"}
CANCEL_MESSAGE="Stopped by user before it finished; partial files are kept in the job folder"
