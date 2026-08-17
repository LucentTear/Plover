"""Plover command plugin: open and close programs by name.

Both commands dispatch on the stroke argument, so adding a program means
adding a table entry here -- no new entry point.

    {PLOVER:LAUNCH:claude}   ->  LAUNCH_TARGETS["claude"]
    {PLOVER:CLOSE:claude}    ->  CLOSE_TARGETS["claude"]
"""

import os
import subprocess

_LOCAL = os.environ.get("LOCALAPPDATA", "")
_PROGRAMS = os.environ.get("ProgramFiles", r"C:\Program Files")
_PROGRAMS_X86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
_WHALE = os.path.join(_PROGRAMS, "Naver", "Naver Whale", "Application", "whale.exe")

# A launch target is either:
#   str  -- handed to ShellExecute: a URL, a document, an executable path, or
#           "shell:AppsFolder\<AppUserModelId>" for a packaged (Store) app.
#   list -- an argv passed straight to Popen, for launchers needing arguments.
#
# Version-numbered paths are avoided wherever an alternative exists. Claude is
# a packaged app, so its AUMID is stable. GitHub Desktop and Discord are
# Squirrel installs keeping versioned app-x.y.z folders, but both ship a stable
# stub at the install root. Obsidian installs to a flat directory.
LAUNCH_TARGETS = {
    "claude": r"shell:AppsFolder\Claude_pzs8sxrjxfjjc!Claude",
    "github": os.path.join(_LOCAL, "GitHubDesktop", "GitHubDesktop.exe"),
    # Discord has no stable stub, only Squirrel's updater, which knows how to
    # find and start the newest app-x.y.z\Discord.exe.
    "discord": [
        os.path.join(_LOCAL, "Discord", "Update.exe"),
        "--processStart",
        "Discord.exe",
    ],
    "obsidian": os.path.join(_LOCAL, "Programs", "Obsidian", "Obsidian.exe"),
    # CELSYS keeps the product folder at "CLIP STUDIO 1.5" across releases, but
    # it is the one launch path here carrying a version number: if a future
    # install moves it, launch() reports the missing path rather than failing
    # silently. This targets PAINT directly, not the CLIP STUDIO hub launcher.
    "clipstudio": os.path.join(
        _PROGRAMS, "CELSYS", "CLIP STUDIO 1.5", "CLIP STUDIO PAINT",
        "CLIPStudioPaint.exe",
    ),
    # Discord DM deep links. The "-/" is a required placeholder in the scheme.
    # These are DM *channel* ids, not user ids: a user id resolves only to a
    # profile, while the channel id opens the conversation itself.
    "dm-f": "discord://-/channels/@me/711465226909777920",
    "dm-p": "discord://-/channels/@me/1264702462619553894",
    "dm-r": "discord://-/channels/@me/988496287043297340",
    # Handing a URL to a running Chromium browser opens it as a new tab in the
    # existing window; if Whale is closed it starts and opens the URL.
    "openmelodies": [_WHALE, "https://openmelodies.online/songmaker"],
    "songmaker": [_WHALE, "http://localhost:3456/songmaker"],
    "studio": [_WHALE, "https://openmelodies.online/blog/studio"],
    "docs": [_WHALE, "https://openmelodies.online/docs"],
    # Colour tools. Routed through Whale explicitly rather than the default
    # browser so the stroke keeps working if the default ever changes.
    "coolors": [_WHALE, "https://coolors.co/generate"],
    "colorwheel": [_WHALE, "https://htmlcolorcodes.com/color-wheel/"],
    "colorpicker": [_WHALE, "https://imagecolorpicker.com/"],
    "ocam": os.path.join(_PROGRAMS_X86, "oCam", "oCam.exe"),
}

# Image names for taskkill. Note the Claude desktop app and the Claude Code
# binary are both named claude.exe; matching is case-insensitive, so closing
# the app also ends the Claude Code session it hosts.
CLOSE_TARGETS = {
    "claude": "Claude.exe",
    "github": "GitHubDesktop.exe",
    "discord": "Discord.exe",
    "obsidian": "Obsidian.exe",
    "clipstudio": "CLIPStudioPaint.exe",
    # The recorder only. Its oCamTask.exe helper is deliberately left running:
    # it has no window for a graceful close to reach, and it runs with an
    # elevated token, so an unelevated Plover cannot terminate it regardless.
    "ocam": "oCam.exe",
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
    target = _resolve(LAUNCH_TARGETS, argument, "launch")

    if isinstance(target, list):
        exe = target[0]
        if not os.path.exists(exe):
            raise FileNotFoundError(f"launch target not installed at {exe}")
        # Detached so the child outlives Plover and inherits none of its handles.
        subprocess.Popen(target, creationflags=subprocess.DETACHED_PROCESS)
        return

    # Bare paths are checked up front; URLs and shell: pseudo-paths are not
    # filesystem paths, so ShellExecute reports those failures itself.
    if os.path.isabs(target) and not os.path.exists(target):
        raise FileNotFoundError(f"launch target not installed at {target}")
    os.startfile(target)


def close(translator, argument):
    images = _resolve(CLOSE_TARGETS, argument, "close")
    if isinstance(images, str):
        images = [images]
    argv = ["taskkill"]
    for image in images:
        argv += ["/IM", image]
    # No /F: taskkill asks the windows to close so the app can save state and
    # shut down cleanly. A hung app may ignore it -- that is the tradeoff.
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    # taskkill exits 128 when nothing matched: closing what is already closed
    # is not an error worth surfacing to Plover.
    if result.returncode not in (0, 128):
        detail = result.stderr.strip()
        if "Access is denied" in detail:
            # Windows forbids a medium-integrity process from terminating a
            # high-integrity one. Nothing here can work around that, so say
            # what the actual remedy is rather than repeating taskkill.
            raise RuntimeError(
                f"{', '.join(images)} is running elevated, so Plover cannot "
                f"close it. Start the program from Plover rather than from a "
                f"tray helper or elevated launcher, or run Plover itself as "
                f"administrator. ({detail})"
            )
        raise RuntimeError(
            f"taskkill failed for {', '.join(images)} "
            f"(exit {result.returncode}): {detail}"
        )
