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
    "ocam": ["oCam.exe", "oCamTask.exe"],
}

# taskkill's graceful mode posts WM_CLOSE to top-level windows, so a process
# without one can never be closed that way. These are terminated with /F
# instead. Only safe for helpers holding no unsaved state -- the recorder
# itself is closed gracefully so it can finalise any recording in progress.
#
# These kills are best effort: oCamTask.exe runs with an elevated token, so
# taskkill is denied unless Plover itself runs elevated. Raising there would
# post a Plover error on every stroke, which is worse than the helper
# surviving, so failures in this group are ignored.
_FORCE_CLOSE = {"oCamTask.exe"}


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


def _taskkill(images, force, required=True):
    argv = ["taskkill"]
    for image in images:
        argv += ["/IM", image]
    if force:
        argv.append("/F")
    result = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    # taskkill exits 128 when nothing matched: closing what is already closed
    # is not an error worth surfacing to Plover.
    if required and result.returncode not in (0, 128):
        raise RuntimeError(
            f"taskkill failed for {', '.join(images)} "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.returncode


def close(translator, argument):
    images = _resolve(CLOSE_TARGETS, argument, "close")
    if isinstance(images, str):
        images = [images]
    # Split so each group gets the only mode that can work on it, and so a
    # failure to force-kill a helper is reported separately from the app.
    graceful = [i for i in images if i not in _FORCE_CLOSE]
    forced = [i for i in images if i in _FORCE_CLOSE]
    if graceful:
        _taskkill(graceful, force=False)
    if forced:
        _taskkill(forced, force=True, required=False)
