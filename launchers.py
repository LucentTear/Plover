"""Plover command plugin: open and close programs by name.

Both commands dispatch on the stroke argument, so adding a program means
adding a table entry here -- no new entry point, no reinstall.

    {PLOVER:LAUNCH:claude}   ->  LAUNCH_TARGETS["claude"]
    {PLOVER:CLOSE:claude}    ->  CLOSE_TARGETS["claude"]
"""

import os
import subprocess

# Anything ShellExecute understands: a URL, a document, an executable path,
# or "shell:AppsFolder\<AppUserModelId>" for a packaged (Store/MSIX) app.
#
# The Claude desktop app is packaged, so its AUMID is used rather than the
# path under Program Files\WindowsApps -- that path embeds the version number
# and breaks on every update, and its ACLs block direct execution anyway.
LAUNCH_TARGETS = {
    "claude": r"shell:AppsFolder\Claude_pzs8sxrjxfjjc!Claude",
}

# Image names passed to taskkill. Note that the Claude desktop app and the
# Claude Code binary are both named claude.exe; matching is case-insensitive,
# so this closes the app and the Claude Code session it hosts together.
CLOSE_TARGETS = {
    "claude": "Claude.exe",
}


def _resolve(table, argument, verb):
    key = argument.strip().lower()
    try:
        return table[key]
    except KeyError:
        raise ValueError(
            f"no {verb} target named {key!r}; "
            f"expected one of: {', '.join(sorted(table))}"
        ) from None


def launch(translator, argument):
    os.startfile(_resolve(LAUNCH_TARGETS, argument, "launch"))


def close(translator, argument):
    image = _resolve(CLOSE_TARGETS, argument, "close")
    # No /F: taskkill asks the window to close so the app can save state and
    # shut down cleanly. A hung app may ignore it -- that is the tradeoff.
    result = subprocess.run(
        ["taskkill", "/IM", image],
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    # taskkill exits 128 when nothing matched, which is not worth surfacing.
    if result.returncode not in (0, 128):
        raise RuntimeError(
            f"taskkill failed for {image} "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )
