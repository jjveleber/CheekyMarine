# App icon design

Date: 2026-11-09. Status: approved in conversation, builder check done.

## Intent

CheekyMarine shows a generic icon in the GNOME taskbar, Alt-Tab and app grid, and it has no app-menu entry at all. The owner wants it to behave like any app installed on Ubuntu desktop: its own icon in the taskbar while running, and a CheekyMarine entry with that icon in the app grid and Activities search.

The icon is the owner's design, chosen on 2026-11-09 after a mockup session: a round badge (rope-tan edge, deep red ring, teal field, colors from the logo) framing a close crop of the logo pirate woman's bare rear with a brass compass-rose plug at the center. It is "Z3", a 2.7x zoom of the earlier "A13" design so the rose dominates. The owner chose the straight zoom over a version with redrawn cheeks. The joke is the point: do not tone it down, recolor or simplify the art.

## Goals

- The icon lives in the repo and ships in every plotter release from now on.
- On an installed tablet (Ubuntu 24.04, GNOME), the running plotter shows the icon in the taskbar/dock and Alt-Tab, on Wayland (Ubuntu default) and on X11.
- CheekyMarine appears in the app grid and Activities search with the icon, and launching it from there runs the same launcher as autostart.
- The autostart entry carries the icon too.

## Non-goals

- Icons on program binaries or folders in the file manager (owner dropped this).
- Changing the in-app logo, splash or About page.
- Cutting the plotter release or the set release. That stays the owner's call after merge.
- An uninstall path (the installer has none today).

## Anti-goals

- Any change to the artwork beyond what the export below needs. The source SVG is final.
- Breaking rollback: rolling back to a set whose plotter bundle has no icon must still succeed.
- A desktop entry that launches a second plotter fighting the first for the screen without the owner knowing. (See "Known behavior, accepted".)

## Source artwork

The final SVG is outside the repo at `~/cheekymarine-icon-z3/cheekymarine-icon-z3.svg` (viewBox 0 0 100 100, 512x512, transparent corners), with `preview-512.png` beside it as the reference render. Copy it in unchanged as `plotter/assets/cheekyplotter.svg`. `~/cheekymarine-icon/` (the earlier A13 design) must stay untouched.

The SVG uses masks, a clip path, radial and linear gradients and a Gaussian blur filter, and references shapes with `<use href=...>`. GNOME renders app icons with librsvg, which supports all of these; Qt's own SVG renderer does not. That is why the design below never has Qt render the icon.

## Decided design

### Repo

- `plotter/assets/cheekyplotter.svg`: the artwork, MIT like the rest of the repo.

### Plotter (`plotter/src/app/main.cpp`, `plotter/CMakeLists.txt`)

- Next to the existing `setApplicationName("cheekyplotter")` (main.cpp line 132), call `QGuiApplication::setDesktopFileName("cheekyplotter")`. On Wayland this sets the window's app_id, which GNOME matches to `cheekyplotter.desktop` to pick the icon.
- `plotter/CMakeLists.txt`: install the SVG to `share/icons/hicolor/scalable/apps/cheekyplotter.svg`, so the `cmake --install` in `scripts/bundle-plotter.sh` puts it in the bundle.

### Bundle (`scripts/bundle-plotter.sh`, `scripts/tests/test_bundle_plotter.sh`)

- The bundle gains `share/icons/hicolor/scalable/apps/cheekyplotter.svg`. Its MANIFEST line is MIT (add the path to the MIT rule; the script fails on any file without a rule). Update the layout comment at the top of the script.
- The bundle test checks the icon is in the tarball.

### Installer (`installer/cheekymarine.sh`)

- New step, run after `unpack_set` (it reads from the set being installed): copy `<set>/plotter/share/icons/hicolor/scalable/apps/cheekyplotter.svg` to `/usr/share/icons/hicolor/scalable/apps/cheekyplotter.svg` (mode 644), then refresh the icon cache (`gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor`) when that command exists. If the set's bundle has no icon (an older plotter release), skip with no error and leave any installed icon in place.
- New app-menu entry `/usr/share/applications/cheekyplotter.desktop` (mode 644), written atomically like the autostart entry:

  ```
  [Desktop Entry]
  Type=Application
  Name=CheekyMarine plotter
  Comment=Chart plotter
  Exec=/opt/cheekymarine/bin/cheekyplotter
  Icon=cheekyplotter
  StartupWMClass=cheekyplotter
  Categories=Utility;
  Terminal=false
  ```

  Then `update-desktop-database -q /usr/share/applications` when that command exists.
- The autostart entry (`install_autostart`) gains `Icon=cheekyplotter` and `StartupWMClass=cheekyplotter`. Everything else in it stays.
- All system paths go through the existing `p` helper so tests run under `CM_ROOT`.
- Tests in `installer/tests/` in the existing Rig style: the icon is copied from the set, a set with no icon installs cleanly, both desktop entries have the expected content and modes, the cache/database commands run when present (shims as needed). Keep the e2e test passing.

### Getting it onto the tablet

Bump `PLOTTER_VERSION` per the usual release flow only when the owner decides to cut releases. Nothing in this change cuts a release.

## Calls made by Claude (owner may override)

- SVG only, no PNG sizes. GNOME renders the scalable icon at every size.
- No `setWindowIcon` fallback in Qt: Qt's SVG renderer cannot draw this artwork, and GNOME matches the window to the desktop entry on both Wayland (app_id from `setDesktopFileName`) and X11 (`StartupWMClass`). This replaces the "window icon fallback for X11" mentioned in conversation.
- The app-menu entry is system-wide (`/usr/share/applications`), not per-user.
- Desktop entry name stays "CheekyMarine plotter", matching autostart.

## Known behavior, accepted (builder check, 2026-11-09)

- No single-instance guard exists: the plotter has no lock file or local server, and the launcher just runs it with `--fullscreen`. Clicking the app in the grid or search while it runs normally focuses the running window, because GNOME matches the window to the entry. A second fullscreen plotter only starts through "New Window" or if matching fails. Claude's call: accept this, add no single-instance logic in this change.
- Release order: the current lock pins plotter 0.2.1, which has no icon. A set release that ships this installer before a plotter release with the icon gets the app-grid entry with a generic icon until the plotter is updated. This follows the "skip with no error" rule. Cut the plotter release first, then the set.
- Rollback calls only `switch_to`, which never touches desktop entries or icons, so rolling back to a bundle with no icon cannot fail on the icon.
- `installer/tests/test_system.py::test_launcher_and_autostart` asserts the exact autostart text and must be updated. The harness's fake plotter tarball has no icon, which already covers the "no icon" case.

## Left to the builder

- Exact function names, where the new installer step sits relative to `install_autostart`, and test file placement.
- How to verify the icon renders correctly under librsvg (for example `rsvg-convert` in CI, compared by eye with `preview-512.png`). The owner checks the result on CapnButts after a release.
