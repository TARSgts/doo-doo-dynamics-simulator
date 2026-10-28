# Personalize the workbench

The top menu is now **File · Settings · Help**. Theme and Cat mode controls have moved out of the header, and Discord controls have moved out of the former Integrations menu.

## Appearance

Choose **Settings → Appearance**:

- **Light:** bright workbench and viewport.
- **Dark:** the original dark blue palette; remains the default.
- **Midnight:** deeper, near-black workbench panels, logs and viewport, with readable foreground colors and blue selection/progress accents.

Exactly one appearance is active. The choice persists in the workspace and synchronizes between desktop windows sharing it. MCP's `set_desktop_theme` accepts `light`, `dark` and `midnight`. Changing appearance does not change the model, create a numerical revision or apply unsaved numerical inputs.

Midnight retains dark-mode rendering contrast in the model viewport and uses a matching background for modal GIF exports. New plot dialogs use their existing dark chart palette, with their own Dark plot checkbox. Published reference reports use a dark background when opened in Midnight; newly generated convergence reports also support the Midnight palette.

## Cat mode

Use **Settings → Cat mode (joke translation)**. The checkmark indicates whether the joke translation is active. Toggle it again to return to English. Its menu label remains English; numerical values, units, user project names and saved solver results are preserved. See [Cat mode](CAT_MODE.md).

## Discord

Use **Settings → Discord Rich Presence…** for the activity-sharing switch and connection status. Custom Application ID controls remain under Advanced settings. Discord preferences are stored for the local user, independently of workspace appearance/language choices. See [Discord setup and privacy](DISCORD_PRESENCE.md).

## Checks

Desktop tests verify menu organization, exclusive appearance selection, persistent Midnight settings, Cat mode round trips, preserved project revisions and unsaved numeric edits. Native Qt checks rendered a real meshed beam in Midnight and confirmed its viewport classes. Claude's modal GIF export was preserved and checked through Qt's embedded browser: its 24-frame output was independently decoded to verify looping, phase symmetry and Midnight background colors. The optional Python browser tests are skipped when Playwright is unavailable.
