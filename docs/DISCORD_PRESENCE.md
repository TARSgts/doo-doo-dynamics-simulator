# Discord Rich Presence

Rich Presence starts automatically on a fresh installation using the simulator's shared Discord identity. Everyone who downloads this version uses the same public Application ID; individual users do not need a Developer Portal application, bot, login flow or configuration. Keep the Discord **desktop** client open and enable activity sharing in Discord. Browser-only Discord cannot receive local IPC presence.

Open **Integrations → Discord Rich Presence…** to see connection status or turn sharing off. A saved off choice remains off after updates; re-enable it and click **Apply** if desired. Optional custom Application ID settings are under **Advanced settings…**.

The simulator's public Application ID, `1564783884363632670`, is prefilled. A custom Application ID can be entered instead. No bot token, OAuth login, password or client secret is used. The application name shown in Discord is configured in the [Discord Developer Portal](https://discord.com/developers/applications). The owner can also set the application's icon there; local Windows icons are not automatically uploaded. There are no uploaded Rich Presence image assets required by this implementation.

Presence shows generic activities such as preparing a model, generating a mesh, solving static structural, calculating natural frequencies, checking mesh convergence or viewing results. It includes the study type and elapsed desktop-session time. It never includes project names, source paths, CAD, materials, forces, stress values, job IDs or exported files. Cat mode does not alter the shared text.

Preferences persist for this Windows user, independently of project workspaces, using Qt settings under `HKEY_CURRENT_USER\Software\TARSgts\DooDooDynamicsSimulator`. Presence is on by default for a fresh installation, and explicit saved off choices are preserved. Disabling it or closing the desktop sends a clear request and closes the local connection. Closing a project switches the activity to the project library rather than retaining a private project name.

## Troubleshooting

- **Waiting for Discord desktop:** open Discord's desktop client. Presence scans its ten local IPC endpoints and retries after 30 seconds when none are available.
- **Connected — activity sent to Discord:** Discord acknowledged the activity. If it is not visible on your profile, check Discord's activity-sharing/privacy settings. Discord controls visibility; acknowledgement is not proof that another user can see it.
- **Rejected connection/activity:** check the Application ID. Paste only its public digits, not a bot token. The dialog includes a Developer Portal link.
- Activity changes are coalesced to at most one update per 15 seconds. A newly connected client receives the latest activity immediately. The displayed elapsed time measures the desktop session, not solve time.
- Discord can be started or restarted after the simulator; reconnects republish the current activity. Missing or unresponsive Discord does not block the UI or interrupt any simulation.

## Implementation and verification

The integration uses the existing PySide6 `QLocalSocket`, backed by named pipes on Windows, and Discord's [official IPC framing, handshake and SET_ACTIVITY protocol](https://github.com/discord/discord-api-docs/blob/main/developers/topics/rpc.mdx). There are no additional downloaded dependencies, listener ports, account tokens or Discord API calls. Only local desktop IPC is opened. The message parser handles fragmented/coalesced frames and bounds payload size. Connection/acknowledgement deadlines and retry timers run asynchronously. RPC errors are shown as connection status, without interrupting the solver.

Fresh-install tests use an empty settings file to confirm the shared ID and enabled default, start the desktop without any developer configuration, and verify that saved opt-outs/custom IDs survive updates. Desktop tests isolate settings and IPC endpoints from the user's actual Discord account. The shared ID has been acknowledged by the owner's Discord client; visibility on every other account has not been independently tested and remains subject to Discord's own settings.

Tests use an isolated local IPC server to verify the handshake, acknowledged activity, ping/pong, throttled updates, clearing, disconnect/retry, rejection and timeouts. Additional tests cover invalid IDs, malformed frames, privacy of activity fields and settings persistence. All 12 presence tests and 39 desktop/plot/Cat mode regression tests passed. A separate live check connected to the actual Discord desktop client with the supplied Application ID and received a successful SET_ACTIVITY acknowledgement; it then cleared its activity.
