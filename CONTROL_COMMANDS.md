# Terminal4GPTWeb Control Command Reference

[한국어](./CONTROL_COMMANDS.ko.md) · [Main README](./README.en.md)

This document is the complete code-level reference for every control command currently exposed by Terminal4GPTWeb.

It covers:

- normal shell input through the Notion **Input** block;
- PTY special keys, Ctrl input, raw byte/text input and resize;
- every Playwright browser subcommand;
- browser observation/Vision rules;
- local `t4g` CLI commands.

> [!IMPORTANT]
> Control syntax such as `:k ENTER`, `:c C`, and `:b ...` must be submitted as a **separate Terminal4GPTWeb Input action**.
> It is not an inline escape syntax that can be appended to ordinary text.
>
> Wrong:
>
> ```text
> hello :k ENTER
> ```
>
> Correct:
>
> ```text
> hello
>
> # after that input is processed, submit a new Input action:
> :k ENTER
> ```
>
> For a TUI such as Codex or Claude Code, send the text first, then send `:k ENTER` by itself if a real Enter key is needed.

---

## 1. Input submission

The Input block has no leading prompt character by default.

Normal shell commands and control commands are submitted when the Input text ends in a **single newline** — one Enter in the Notion UI.

Example:

```text
pwd
```

This prevents polling from executing partially typed text. **Seeing the command text in Input does not mean it has been submitted.** If the command remains visible and nothing runs, check for a missing trailing newline first.

When an agent edits Input through a Notion API/connector, make sure the actual Input content ends with a newline, e.g. `pwd\n`. For connectors that edit the page as Markdown code blocks, leave one blank line after the action before closing the code fence so the trailing newline is preserved.

Example:

```markdown
```bash
pwd

```
```

### Input size limit

Normal shell input and `:send` accept at most **4000 bytes** per submission (UTF-8, including the final Enter). The limit fits the kernel tty input buffer (4096 bytes).

Oversized input is not sent to the PTY at all. Input is reset and the Terminal block shows:

```text
[Terminal4GPTWeb] Input not sent: 5123 bytes exceeds the 4000-byte limit (UTF-8). Split it into smaller submissions.
```

Write long files in several submissions, e.g. repeated `cat >> file <<'EOF'` chunks.

Use one action per submission:

```text
observe
→ write one action
→ wait for Input to reset to empty
→ observe the result
→ send the next action
```

---

## 2. Normal shell command

Syntax:

```text
<shell command>
```

Examples:

```text
pwd

git status

cd ~/project

python3
```

Terminal4GPTWeb uses one persistent PTY rather than spawning a new shell for every command, so cwd, environment, foreground processes, REPLs and TUI state persist.

Multi-line shell text is sent as terminal Enter-separated input and an Enter is appended at the end.

---

# PTY control commands

## 3. Immediate Ctrl tokens

These five tokens are recognized **without the trailing newline**:

| Token | Control | Typical use |
| --- | --- | --- |
| `^C` | Ctrl-C | interrupt foreground process |
| `^D` | Ctrl-D | EOF |
| `^Z` | Ctrl-Z | suspend |
| `^L` | Ctrl-L | clear/redraw |
| `^\\` | Ctrl-\\ | quit signal |

Example:

```text
^C
```

---

## 4. `:ctrl` / `:c`

Send an ASCII control character.

Syntax:

```text
:ctrl <key>
:c <key>
```

Examples:

```text
:c C

:c O

:ctrl X

:ctrl BACKSLASH
```

Supported keys are the ASCII control range:

```text
@
A ... Z
[
\
]
^
_
```

Input is normalized to uppercase. `BACKSLASH` is also accepted for Ctrl-\\.

Common examples:

| Command | Result |
| --- | --- |
| `:c A` | Ctrl-A |
| `:c C` | Ctrl-C |
| `:c D` | Ctrl-D |
| `:c L` | Ctrl-L |
| `:c O` | Ctrl-O |
| `:c X` | Ctrl-X |
| `:c [` | ESC control byte |
| `:c BACKSLASH` | Ctrl-\\ |

---

## 5. `:key` / `:k`

Send a PTY special-key escape sequence.

Syntax:

```text
:key <name>
:k <name>
```

Canonical keys:

```text
UP
DOWN
LEFT
RIGHT
HOME
END
PAGEUP
PAGEDOWN
INSERT
DELETE
TAB
ENTER
ESC
ESCAPE
BACKSPACE
F1 ... F12
```

Aliases:

| Alias | Key |
| --- | --- |
| `PGUP` | `PAGEUP` |
| `PGDN` | `PAGEDOWN` |
| `DEL` | `DELETE` |
| `INS` | `INSERT` |
| `RETURN` | `ENTER` |
| `RET` | `ENTER` |
| `ENT` | `ENTER` |
| `BS` | `BACKSPACE` |
| `BKSP` | `BACKSPACE` |

Names are case-insensitive and underscores are removed before lookup.

Examples:

```text
:k ENTER

:key UP

:k PGDN

:k ESC

:k F5
```

This is especially useful for TUIs that distinguish pasted text from a real Enter key.

`:k ENTER` must be a separate Input submission. Do not append it to the text being sent to the TUI. Send the text first, wait for that Input action to finish, then submit `:k ENTER` alone.

---

## 6. `:send` / `:s`

Send decoded raw text/bytes directly to the current foreground PTY instead of executing a shell line.

Syntax:

```text
:send <text>
:s <text>
```

Supported escapes:

| Input | Sent value |
| --- | --- |
| `\n` | LF |
| `\r` | CR |
| `\t` | Tab |
| `\e` | ESC (`0x1b`) |
| `\\` | backslash |
| `\xNN` | two-digit hex character/byte |

Examples:

```text
# vim: save and quit
:s \e:wq\r

# vim: quit without saving
:s \e:q!\r

# ESC
:s \e
```

Unknown escape spellings preserve the backslash rather than silently dropping it.

---

## 7. `:resize` / `:rs`

Resize the PTY.

Syntax:

```text
:resize <columns>x<rows>
:rs <columns>x<rows>
```

Examples:

```text
:rs 140x50

:resize 100x30
```

Allowed range:

```text
columns: 20 .. 400
rows:     5 .. 200
```

Uppercase `X` and spaced forms are accepted by the parser:

```text
:rs 120X40
:rs 120 x 40
```

Resize updates the outer PTY, pyte screen and the running application via SIGWINCH. With SRT enabled, the inner `script` PTY is signalled as well.

---

# Browser / Playwright control

## 8. `:browser` / `:b`

Browser command wrapper.

Syntax:

```text
:browser <browser command>
:b <browser command>
```

Example:

```text
:b goto https://example.com
```

Current browser subcommands:

```text
goto
open
shot
save
full
full-tiles
clear-saved
click
move
drag
scroll
type
key
back
reload
```

`open` is an alias for `goto`.

Chromium starts lazily on the first browser command and the same context/page stays alive until the daemon stops or restarts. Cookies, login state, local/session storage, focus and browser history can therefore persist across actions.

---

## 9. `:b goto <url>` / `:b open <url>`

Navigate to a URL.

```text
:b goto <url>
:b open <url>
```

Example:

```text
:b goto https://example.com
```

The controller calls Playwright `page.goto(..., wait_until="domcontentloaded")`, waits the configured `settle_ms`, then publishes a fresh observation.

Navigation resets the remembered mouse cursor position.

Exactly one URL argument is accepted.

---

## 10. `:b shot`

Capture a fresh observation without interacting.

```text
:b shot
```

Useful when:

- a SPA renders later than the normal settle delay;
- animations/loading completed after the previous action;
- current page state is uncertain after a failure;
- you only need a fresh Screenshot/Vision payload.

---

## 10A. `:b save [label]` — keep the current viewport

Copy the latest viewport screenshot into **Browser Saved Snapshots** so it remains visible after navigation or later browser actions.

```text
:b save
:b save result A
```

- An existing observation is required; run `:b shot` first if needed.
- The label is optional. The current page title/URL is used when omitted.
- The live Browser Screenshot and current observation_id are not changed.
- Saved captures are temporary and are cleared by `:b clear-saved` or daemon restart.

---

## 10B. `:b full [label]` — save one full-width long screenshot

Capture the entire document as **one full-height PNG fitted to the browser viewport width** and store it under Browser Saved Snapshots.

```text
:b full
:b full long report
```

Normal web pages use the Playwright viewport width for the full-page screenshot. When an image is opened directly in Chrome, Terminal4GPTWeb bypasses the browser's fit-to-height viewer and extracts the `<img>` element's **natural pixels** directly. Images wider than the configured viewport are downscaled proportionally; viewer side margins are never part of the saved image.

- The long page is not split into multiple images.
- A fresh live observation is published after the full capture, so use the new observation_id for subsequent coordinate actions.
- The saved full image is for inspection/comparison; coordinate actions still use the live Browser Screenshot.

### Optional: `:b full-tiles [label]`

Use the previous viewport-height tile view only when it is explicitly useful.

```text
:b full-tiles long report
```

Up to 20 tiles are saved.

---

## 10C. `:b clear-saved` — remove temporary captures

```text
:b clear-saved
```

Remove all saved viewport/full-page tiles without affecting the live Browser Screenshot.

---

## 11. `:b move <observation_id> <x> <y>`

Move the mouse / create hover state.

```text
:b move <observation_id> <x> <y>
```

Example:

```text
:b move obs_20261002T040000Z_0003 620 240
```

The supplied observation ID must be current.

Because `move` itself publishes a new observation, a click after a hover must use the **new** ID produced by the move.

---

## 12. `:b click <observation_id> <x> <y>`

Click viewport coordinates.

```text
:b click <observation_id> <x> <y>
```

Example:

```text
:b click obs_20261002T040000Z_0004 640 418
```

Coordinates are **viewport-relative CSS pixels**, not document coordinates.

For the default `1280x720` viewport:

```text
top-left     = 0,0
bottom-right = 1280,720
```

Out-of-viewport coordinates are rejected.

---

## 13. `:b drag <observation_id> <x1> <y1> <x2> <y2>`

Drag from one viewport coordinate to another.

```text
:b drag <observation_id> <x1> <y1> <x2> <y2>
```

Internally:

1. move to start;
2. mouse down;
3. move to destination in 8 steps;
4. mouse up.

The final cursor position is recorded as the destination point.

---

## 14. `:b scroll <dx> <dy>`

Mouse-wheel scroll.

```text
:b scroll <dx> <dy>
```

Examples:

```text
:b scroll 0 600
:b scroll 0 -600
:b scroll 400 0
```

- positive `dy`: down;
- negative `dy`: up.

The Browser Status `scroll: x,y` field is the current `window.scrollX,window.scrollY`, but click/move/drag coordinates always remain viewport-relative.

---

## 15. `:b type <text>`

Insert literal text into the currently focused browser element.

```text
:b type <text>
```

Examples:

```text
:b type user@example.com

:b type hello world
```

This uses Playwright `keyboard.insert_text()`.

Important:

- it does not press Enter;
- it does not interpret text as keyboard shortcuts;
- an editable element must already have focus.

A reliable form sequence is:

```text
click field
→ wait for new observation
→ type
→ wait
→ key Tab or key Enter
```

---

## 16. `:b key <key>`

Press one Playwright browser key.

```text
:b key <key>
```

Examples:

```text
:b key Enter
:b key Tab
:b key Escape
:b key ArrowDown
:b key Shift+Tab
:b key Control+A
```

The argument is passed to Playwright `keyboard.press()`.

This is a different key namespace from PTY `:k ENTER`.

Typical Playwright key names include:

- `Enter`
- `Tab`
- `Escape`
- `Backspace`
- `Delete`
- `ArrowUp` / `ArrowDown` / `ArrowLeft` / `ArrowRight`
- `Home` / `End`
- `PageUp` / `PageDown`
- modifier combinations such as `Control+A`, `Shift+Tab`

---

## 17. `:b back`

Go back in browser history.

```text
:b back
```

Waits for `domcontentloaded`, then publishes a fresh observation.

No extra arguments are accepted.

---

## 18. `:b reload`

Reload the current page.

```text
:b reload
```

Waits for `domcontentloaded`, then publishes a fresh observation.

No extra arguments are accepted.

---

# Browser observation rules

## 19. Browser Status

During execution:

```text
status: running
command: ...
viewport: 1280x720
```

On success:

```text
status: ready
observation_id: obs_...
url: ...
title: ...
viewport: 1280x720
scroll: 0,0
cursor: none
vision: ready (jpeg quality ...)
vision_page_url: ...
created_at: ...
```

On failure:

```text
status: failed
command: ...
error: ...
viewport: ...
```

Prefer issuing the next browser action only after `status: ready`.

---

## 20. observation_id

Every successful browser action creates a new observation ID.

Example:

```text
obs_20261002T040000Z_0007
```

These coordinate actions require the latest ID:

- `move`
- `click`
- `drag`

A stale ID fails with:

```text
STALE_OBSERVATION
```

Recommended loop:

```text
read ready Browser Status
→ record observation_id
→ inspect matching Screenshot/Vision
→ issue one action
→ wait for next ready observation
→ discard previous ID
→ repeat
```

---

## 21. Browser Screenshot

The control page contains the latest viewport PNG.

It is:

- viewport-only, not full-page;
- captured at CSS scale;
- in the same viewport coordinate system used by mouse actions.

Scroll before interacting with off-screen content.

---

## 22. Browser Vision Payload

A separate child page stores the compressed JPEG payload for GPT image reasoning.

Format:

```text
observation_id: obs_...
mime: image/jpeg
encoding: base64
viewport: 1280x720
quality: 35
data_base64:
...
```

Verify that this `observation_id` matches Browser Status before using the image for coordinate reasoning.

If the configured JPEG is too large, capture quality is retried in this order:

```text
configured quality
→ 25
→ 15
→ 8
```

If none fit `vision_max_base64_chars`, the observation fails.

---

## 23. Cursor overlay

With:

```toml
show_cursor_overlay = true
```

the last mouse position is drawn as a small marker in subsequent screenshots.

It is updated by:

- move
- click
- drag

and reset by navigation.

---

## 24. Browser failure recovery

### STALE_OBSERVATION

Reread Browser Status/Screenshot and recompute coordinates using the new ID.

### Coordinate outside viewport

Scroll first or choose a coordinate inside the configured viewport.

### Late SPA/async rendering

Run:

```text
:b shot
```

to recapture without another interaction.

### Missing Chromium

```bash
playwright install chromium
```

### Vision payload too large

Reduce viewport size or adjust `vision_max_base64_chars`.

---

## 25. Current browser-control scope

The current Notion command surface exposes:

- one persistent Playwright browser context;
- one controlled page;
- viewport mouse control;
- keyboard control;
- screenshot;
- Vision payload.

It does not currently expose commands for:

- CSS-selector click;
- DOM query/locator;
- automatic popup/new-tab switching;
- file chooser/upload;
- download management;
- browser forward;
- explicit browser close/restart;
- multiple controlled tabs.

A newly opened tab/window is not automatically adopted as the controlled page.

---

# Local t4g CLI

## 26. `t4g init`

Run the initial setup wizard.

```bash
t4g init
t4g init --config /path/to/config.toml
```

---

## 27. `t4g reinit`

Recreate Notion control/runtime pages while keeping the local terminal/browser configuration.

```bash
t4g reinit
t4g reinit --config /path/to/config.toml
```

---

## 28. `t4g run`

Run the daemon in the foreground.

```bash
t4g run
t4g run --config /path/to/config.toml
```

Useful for debugging.

---

## 29. `t4g doctor`

Validate configuration and dependencies.

```bash
t4g doctor
t4g doctor --config /path/to/config.toml
```

Checks include config, Linux/WSL, shell/cwd, SRT dependencies/smoke test, Playwright package and Notion runtime blocks.

---

## 30. `t4g daemon start`

Start the detached daemon.

```bash
t4g daemon start
t4g daemon start --config /path/to/config.toml
```

---

## 31. `t4g daemon stop`

Stop the detached daemon.

```bash
t4g daemon stop
```

---

## 32. `t4g daemon restart`

Restart the daemon.

```bash
t4g daemon restart
t4g daemon restart --config /path/to/config.toml
```

---

## 33. `t4g daemon status`

Show daemon state.

```bash
t4g daemon status
t4g daemon status --config /path/to/config.toml
```

---

## 34. `t4g daemon logs`

Show daemon logs.

```bash
t4g daemon logs
```

Default: last 100 lines.

Choose count:

```bash
t4g daemon logs -n 300
t4g daemon logs --lines 300
```

Follow:

```bash
t4g daemon logs -f
t4g daemon logs --follow
```

Combine:

```bash
t4g daemon logs -n 300 -f
```

---

## 35. Common CLI options

Version:

```bash
t4g --version
```

Help:

```bash
t4g --help
t4g daemon --help
```

Commands that accept a config path use:

```bash
--config /path/to/config.toml
```

Default:

```text
~/.config/t4g/config.toml
```

---

# Quick reference

## Input control

| Function | Command |
| --- | --- |
| shell line | `<command>` + single newline |
| Ctrl | `:ctrl KEY`, `:c KEY` |
| special key | `:key NAME`, `:k NAME` |
| raw input | `:send TEXT`, `:s TEXT` |
| resize | `:resize COLSxROWS`, `:rs COLSxROWS` |
| browser | `:browser ...`, `:b ...` |
| immediate Ctrl | `^C`, `^D`, `^Z`, `^L`, `^\\` |

## Browser subcommands

| Function | Command |
| --- | --- |
| navigate | `:b goto <url>` / `:b open <url>` |
| observe | `:b shot` |
| save current viewport | `:b save [label]` |
| save long page as one full-width image | `:b full [label]` |
| save long page as tiles (optional) | `:b full-tiles [label]` |
| clear saved captures | `:b clear-saved` |
| move/hover | `:b move <obs> <x> <y>` |
| click | `:b click <obs> <x> <y>` |
| drag | `:b drag <obs> <x1> <y1> <x2> <y2>` |
| scroll | `:b scroll <dx> <dy>` |
| text | `:b type <text>` |
| key | `:b key <key>` |
| back | `:b back` |
| reload | `:b reload` |
