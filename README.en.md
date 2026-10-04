# Terminal4GPTWeb

[한국어](./README.md) · [GPT bootstrap prompt](./GPT_PROMPT.md) · [Control commands](./CONTROL_COMMANDS.md) · [Detailed installation](./INSTALL.md)

**Give web-based AI agents controlled access to a real development environment without exposing a shell server to the internet.**

`Terminal4GPTWeb` uses Notion as a **control bridge between a web AI client and a local Linux PTY / Playwright runtime**.

GitHub and Notion connectors are good at providing **context** from code, issues, PRs, and documents. Terminal4GPTWeb adds the missing **execution and verification layer** on the user's actual machine.

When a web AI client can read and edit the generated Notion page, it can:

- run real shell commands such as `git`, builds, unit tests, and integration tests;
- use locally installed tools such as Docker, Kubernetes, SSH, and cloud CLIs;
- inspect the current terminal screen and keep a persistent PTY session alive;
- send real key events such as Enter, arrows, and Ctrl-C and interact with TUIs;
- use terminal applications such as `nano`, `vim`, `less`, `top`, and Codex;
- drive a Playwright browser and verify web UIs end to end;
- optionally run the shell inside [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime), with filesystem and network limits and credential masking.

In short:

> **Web AI ↔ Notion ↔ Terminal4GPTWeb ↔ PTY / Playwright ↔ WSL / Linux / Web**

Notion is not the destination of the product. It acts as a **transport / control surface** that web AI clients can access, while the local daemon owns the real terminal and browser sessions.

Terminal4GPTWeb is not tied to a specific model provider. Any web AI client that can reliably read and edit the generated Notion page can use the same bridge. The current documentation describes the ChatGPT Web workflow in the most detail.

> [!CAUTION]
> PTY sandboxing is **optional**. With `sandbox.enabled = false` (the default), anything written to Input runs with the permissions of the Linux user running the daemon. With `sandbox.enabled = true` the shell runs inside [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime), which adds filesystem, network and credential-masking rules, but it does not replace normal secret-management practices.

---

## Why this exists

Web AI connectors for GitHub and Notion are useful for reading and writing remote context such as repositories, issues, PRs, and documents. But those connectors do not by themselves run `npm test`, `pytest`, `kubectl`, `docker`, SSH sessions, local servers, or browser E2E flows inside the user's real development environment.

Terminal4GPTWeb fills that **gap between connectors and runtime execution**:

1. The web AI reads the **Terminal** block.
2. The web AI writes a command or key event to the **Input** block.
3. `t4g` polls that block and forwards the input to a real PTY.
4. The PTY screen is rendered back into the **Terminal** block.
5. The web AI reads the updated state and continues.
6. When needed, it uses the same control path to drive Playwright and verify the resulting UI.

It is not a replacement for SaaS connectors. It turns the context those connectors provide into **execution and verification on the real machine**.

No public SSH endpoint, custom web server, database, or message queue is required.

---

## Architecture

```text
┌──────────────────────┐
│    Web AI client     │
│   Notion connector   │
└──────────┬───────────┘
           │ read / edit
           ▼
┌──────────────────────┐
│     Notion page      │
│                      │
│  Terminal code block │◄─────────────┐
│  Input code block    │──────────────┐│
└──────────────────────┘              ││
                                      ││ Notion API
                                      ││
                              ┌───────▼▼────────┐
                              │   t4g daemon    │──► Playwright Chromium
                              └───────┬─────────┘
                                      │
                                      ▼
                              ┌─────────────────┐
                              │ persistent PTY  │
                              └───────┬─────────┘
                                      │ sandbox.enabled = true
                                      ▼
                         ┌───────────────────────────┐
                         │ srt (optional)            │
                         │  bubblewrap fs rules      │
                         │  network allowlist proxy  │
                         │  credential masking       │
                         └────────────┬──────────────┘
                                      │
                                      ▼
                              Bash / TUI on WSL / Linux
```

The Terminal block is a **screen snapshot**, not an append-only stdout log. ANSI cursor movement, clearing, scrolling, and redraw sequences are interpreted locally with `pyte` before the screen is written back to Notion.

That is why redraw-oriented applications can work at a text-UI level.

---

## What it can do

- Persistent interactive Bash session
- Real PTY semantics: `isatty(stdin/stdout/stderr) == true`
- ANSI / VT screen emulation
- Shell state persistence
- Foreground-process stdin
- Ctrl-C / Ctrl-D / Ctrl-Z / Ctrl-L / Ctrl-\\
- Arrow keys, Home/End, Page Up/Down
- Enter, Backspace, Delete, Insert, Tab, Esc
- F1-F12
- Raw byte / escape-sequence input
- Runtime terminal resize
- Persistent Playwright Chromium session
- Browser screenshots published to Notion
- Compact JPEG Vision payload on an isolated Notion child page
- Observation-ID guarded mouse move/click/drag/scroll
- Browser keyboard input and navigation
- Detached background daemon
- Single-instance locking
- Runtime block self-healing
- `doctor` diagnostics
- Optional srt PTY sandbox: read-only / workspace filesystem isolation, write allow/deny lists, outbound domain allowlist
- Claude Code-style credential masking for files and environment variables: the shell sees `fake_value_<uuid>`, allowed HTTPS requests carry the real value

Tested interaction patterns include Bash, Python REPL, nano, vim-style key sequences, Codex TUI, interactive prompts, and long-running processes interrupted with Ctrl-C.

---

## Requirements

- WSL2 Ubuntu or another Linux environment
- Python 3.11+
- Bash
- A Notion API token: Personal Access Token or Internal Connection token
- A Notion page to use as the parent for generated Terminal4GPTWeb pages
- A web AI client with a **Notion connection that can read and edit the generated page**
- ChatGPT Web is the reference client documented most extensively here
- Optional but recommended for development: the AI client's **GitHub connection**
- Optional for recurring operations: ChatGPT scheduled tasks / automations, where available
- Only for sandbox mode: Node.js 22.12+, [`@anthropic-ai/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime) **0.0.78** (`srt`, currently tested version), `bubblewrap`, `socat`, `ripgrep`, and `script` (util-linux)

> [!IMPORTANT]
> Terminal4GPTWeb does not expose a standalone GPT API. GPT Web reaches the local runtime by reading and editing the generated Notion pages, so the Notion connection is required for the GPT-Web workflow.

---

## First-time installation and setup

For a completely new installation, see **[INSTALL.md](./INSTALL.md)**. It covers the Notion Developer portal, token creation, parent-page access, Linux packages, Playwright, the wizard, sandbox configuration, ChatGPT's Notion connection, and the first smoke test.

The short version is below.

### 1. Prepare a Notion parent page

Create an empty Notion page, for example:

```text
Terminal4GPTWeb Root
```

The current `t4g init` flow creates the generated control page under a parent page. You can select it by search in the wizard, so copying its URL in advance is optional.

### 2. Obtain a Notion API token

The **local daemon** needs a Notion API token. This is separate from the Notion app/plugin connection used by ChatGPT Web.

You can use either:

- a **Personal Access Token (PAT)** for a trusted personal CLI workflow; or
- an **Internal Connection** token for a dedicated bot identity.

For an Internal Connection, grant it access to the parent page and enable content permissions needed to read, insert, and update page content.

Official Notion guides:

- https://developers.notion.com/guides/get-started/quick-start
- https://developers.notion.com/guides/get-started/internal-connections

### 3. Install the local package

```bash
git clone https://github.com/hyeongmin90/terminal4gptweb.git
cd terminal4gptweb

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
playwright install chromium
```

Only if you plan to enable the PTY sandbox (Ubuntu/WSL2, Node.js 22.12+):

```bash
sudo apt install -y bubblewrap socat ripgrep util-linux
npm install -g @anthropic-ai/sandbox-runtime@0.0.78
srt --version
```

Without `sandbox.enabled = true` none of these are needed.

Verify:

```bash
t4g --version
t4g --help
```

If an editable install stops working after the repository directory is renamed or moved:

```bash
cd ~/terminal4gptweb
pip install -e .
hash -r
```

### 4. Run the setup wizard

```bash
t4g init
```

The wizard asks for the Notion API token and then offers:

```text
Choose parent Notion page

  1. Search pages
  2. Enter URL / page ID
```

It also asks for the shell, initial working directory, terminal size and whether to enable the srt PTY sandbox (plus its filesystem and network options).

The generated Notion structure is:

```text
Parent Page
└─ Terminal4GPTWeb
   ├─ Terminal / Input / Browser
   ├─ Terminal4GPTWeb Help
   └─ Browser Vision Payload
```

Local config is stored at:

```text
~/.config/t4g/config.toml
```

### 5. Validate and start

```bash
t4g doctor
t4g daemon start
t4g daemon status
```

### 6. Connect Notion in ChatGPT Web

This is a **second, separate connection** from the local API token.

Connect Notion from ChatGPT Apps/Plugins, sign in to the account/workspace containing the generated page, and approve access to the relevant content.

OpenAI setup guide:

https://help.openai.com/en/articles/12532955-notion-app-and-setup-in-chatgpt

### 7. First smoke test

In the generated Notion Input block:

```text
pwd
```

Press Enter once to submit. Terminal should update and Input should reset to an empty block.

Browser:

```text
:b goto https://example.com
```

Browser Status and Browser Screenshot should update.

If the whole generated page is deleted later:

```bash
t4g reinit
t4g daemon restart
```

---

## First-time GPT setup

For a new ChatGPT Web conversation, paste the **[GPT bootstrap prompt](./GPT_PROMPT.md)** as the first message.

It tells GPT to read the generated Notion `Terminal4GPTWeb Help` page first, then use Terminal/Input/Browser with the correct `observe → act → observe` protocol. The bootstrap prompt intentionally stays short; the Help page and [CONTROL_COMMANDS.md](./CONTROL_COMMANDS.md) remain the source of truth.

---

## Recommended web-AI setup (ChatGPT reference)

Terminal4GPTWeb is not tied to one web AI client. The configuration below uses **ChatGPT Web as the current reference workflow** because it is the most extensively documented here. Other clients can use the same control flow when they can read and edit the generated Notion page.

### 1. Notion — required

Connect Notion to ChatGPT and make the generated Terminal4GPTWeb page accessible to that connection.

The Notion connection is the transport used by GPT Web:

```text
GPT Web
  ↓ read/write through Notion
Terminal4GPTWeb control page
  ↓ polled by local daemon
PTY / Playwright
```

Without the Notion connection, the local daemon still works, but GPT Web cannot use the generated page as its terminal/browser tool surface.

### 2. GitHub — recommended for development

Connect GitHub when you want GPT to work with repository context in addition to the local runtime.

A useful development loop is:

```text
GitHub
  ↓ issue / PR / history / code context
GPT Web
  ↓
Notion → Terminal4GPTWeb
  ↓
edit / build / unit test / integration test
  ↓
Playwright + Vision
  ↓
browser E2E verification
```

This lets GPT use GitHub for repository-level context while using the local terminal for commands that must run on your machine.

Example requests:

```text
Review the latest changes in this repository, run the relevant tests locally,
and verify the web UI with Playwright.

Check the linked issue, reproduce it locally, fix it, run the test suite,
then verify the affected screen through Browser Vision.
```

### 3. Scheduled tasks / automations — optional for OPS

If your ChatGPT client supports scheduled tasks or automations, Terminal4GPTWeb can also act as an operations surface.

A scheduled task can periodically ask GPT to:

- inspect `docker ps`, service/process state, disk and memory usage;
- call local health endpoints;
- inspect recent logs for errors;
- run a lightweight browser smoke test;
- report only when a check fails or needs attention.

Example OPS instruction:

```text
Every morning, inspect my Terminal4GPTWeb page.
Run the service health checklist, check recent error logs,
and verify the main web page with Playwright.
Notify me only if something needs attention.
```

Keep recurring checks read-only where possible. Do not put credentials, sudo passwords, private keys, or other secrets into the Notion Input block.

---

## How web AI / agents should operate

For reliable agent behavior, use a strict observe → act → observe loop:

1. Read **Terminal** or **Browser Status**.
2. Write exactly one command/action to **Input**.
3. Wait until Input resets to an empty block.
4. Read the refreshed output before issuing the next action.
5. For browser coordinate actions, use only the latest `observation_id`.
6. When Vision is needed, fetch `vision_page_url`, decode `data_base64` as JPEG, and verify that its observation ID matches Browser Status.
7. Stop and surface the error when Browser Status is `failed`; do not continue with stale coordinates.
8. **The actual Input text must end with a newline before it is executed.** Writing only the command text without the final line break leaves it as incomplete input. In the Notion UI, press Enter once after the action. Through an API/connector, preserve a trailing `\n`; for Markdown-style code-block edits, leave one blank line after the action before closing the code block. If a command stays visible in Input instead of running, check the trailing newline first.
9. If Input shows `[SANDBOX UNAVAILABLE]`, the sandbox is enabled but srt or one of its tools is missing; report it rather than retrying commands.

This protocol is also documented in the generated **Terminal4GPTWeb Help** Notion child page.

---

## Example workflows

### Development + test

```text
GitHub context
→ inspect code / issue / PR
→ run local build and tests through Terminal
→ start the application
→ open it with Playwright
→ inspect with Vision
→ interact and verify the result
```

### Local troubleshooting

```text
read Terminal
→ inspect process/container state
→ inspect logs
→ run health request
→ apply a fix
→ restart service
→ verify again
```

### Browser E2E

```text
:b goto <url>
→ read latest Vision payload
→ choose coordinates
→ :b click <obs_id> <x> <y>
→ wait for new observation
→ verify the changed screen
```

### OPS / recurring checks

Use a fixed, minimal checklist such as:

```text
1. process/container status
2. health endpoint
3. recent ERROR logs
4. disk + memory
5. browser smoke test
```

For automated runs, prefer notifications only on actionable failures rather than sending a success message every time.

---

## Run as a background daemon

For normal use:

```bash
t4g daemon start
```

Lifecycle commands:

```bash
t4g daemon status
t4g daemon restart
t4g daemon stop
t4g daemon logs
t4g daemon logs -f
```

Runtime files:

```text
~/.cache/notion_is_terminal/daemon.pid
~/.cache/notion_is_terminal/daemon.log
~/.cache/notion_is_terminal/instance.lock
```

The daemon survives closing the WSL terminal window. It does not currently auto-start after WSL itself shuts down or Windows reboots.

Foreground mode is available for debugging:

```bash
t4g run
```

---

## Using it from a web AI client

Once the generated Notion page is readable and editable through a web AI client's Notion connector, the page becomes a **terminal and browser execution surface** for that client.

A typical flow:

```text
You:
Check my Terminal4GPTWeb page and run git status.

GPT:
1. reads the Terminal block
2. writes "git status" to Input
3. waits for the daemon to execute it
4. reads the refreshed Terminal block
5. explains the result
```

Because the underlying PTY is persistent, GPT can continue with:

```bash
cd ~/project
git status
python3
codex
nano notes.txt
```

without creating a new shell for every request.

## Control commands

The complete control protocol is documented separately:

- **[Control Command Reference](./CONTROL_COMMANDS.md)** — every Input command, PTY key/alias, Ctrl input, raw escape, resize rule, Playwright browser command, observation rule and local `t4g` CLI command.
- [한국어 제어 명령 전체 레퍼런스](./CONTROL_COMMANDS.ko.md)

The main control pattern is intentionally simple:

```text
observe current Terminal / Browser Status
→ write one action to Input
→ wait for Input to reset
→ observe the new state
→ continue
```

A few examples:

```text
git status

:k ENTER

:c C

:b goto https://example.com

:b shot
```

Control commands such as `:k ENTER` are **separate Input actions**, not inline syntax appended to ordinary text. For example, send text to Codex first, then submit `:k ENTER` alone in the next Input action if a real Enter key is needed.

The underlying PTY is persistent, so cwd, environment, REPLs and TUI state continue across actions.

### Browser + Vision overview

The daemon also keeps one persistent Playwright Chromium context/page. Browser state such as cookies, login state, local/session storage, focus and history can survive across browser actions.

Each successful browser action publishes a fresh observation:

```text
Browser Status
  status / observation_id / url / title
  viewport / scroll / cursor
  vision_page_url

Browser Screenshot
  latest viewport PNG

Browser Saved Snapshots
  temporary viewport / full-width long screenshots kept for comparison

Browser Vision Payload
  compressed JPEG + matching observation_id
```

Coordinate actions are guarded by the current `observation_id`, preventing old screenshot coordinates from being applied after the page changes.

Before navigating away from a result you want to compare, use `:b save [label]` to keep the current viewport under **Browser Saved Snapshots**. For a vertically long page, `:b full [label]` saves **one full-height screenshot fitted to the viewport width**. Browser-native image documents bypass Chrome's fit-to-height viewer and use the image's natural pixels directly, so viewer side margins are not captured. The older tiled view remains available as `:b full-tiles [label]` when explicitly useful. Use `:b clear-saved` to remove temporary captures; they are also cleared on daemon restart. The live **Browser Screenshot** remains a single viewport image so coordinate reasoning stays exact.

The full browser command syntax, coordinate rules, focus/keyboard behavior, hover workflow, failure recovery and current limitations are all in **[CONTROL_COMMANDS.md](./CONTROL_COMMANDS.md)**.

---

## Runtime block self-healing

The Notion page ID is the durable anchor. Terminal and Input block IDs are replaceable runtime references.

Every `health_check_interval` seconds, each runtime block is validated independently.

If one block is deleted, trashed, invalid, or moved away from its expected position:

1. the healthy block is kept unchanged;
2. only the damaged block is recreated;
3. it is inserted back at its original section;
4. only the changed block ID is persisted to `config.toml`.

If both runtime blocks are removed, both are recreated.

If the stable Terminal/Input anchor sections are also removed, recovery falls back to creating a fresh runtime section at the end of the page.

If the page itself is deleted or inaccessible, the daemon stops instead of silently creating another page.

To intentionally recreate a deleted full control page, run:

```bash
t4g reinit
t4g daemon restart
```

`reinit` preserves the existing local terminal/browser settings and replaces the Notion page and runtime block IDs in the config.

---

## PTY sandbox (srt)

By default the shell runs with the full permissions of the user running the daemon. Setting `sandbox.enabled = true` runs it inside [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime), the sandbox runtime behind Claude Code's sandboxed Bash. t4g does not reimplement the sandbox: it translates `[sandbox]` into an srt settings file and launches the shell through srt.

```text
sandbox.enabled = false   →  bash                                  (srt not needed)
sandbox.enabled = true    →  srt -s ~/.cache/notion_is_terminal/srt-settings.json \
                               -- script -qfec "bash --rcfile … -i" /dev/null
```

srt applies three layers:

| Layer | What it does |
| --- | --- |
| Filesystem | bubblewrap mounts: writes denied except allowed paths; selected paths hidden |
| Network | the shell gets its own network namespace; all traffic goes through srt's proxy, which only lets `allowed_domains` through |
| Credentials | configured files and environment variables are replaced by `fake_value_<uuid>` inside the shell; the proxy swaps in the real value on requests to allowed hosts |

`script` gives the shell a controlling terminal inside srt's session, so job control and Ctrl-C keep working. Terminal resize (`:rs`) is relayed to it as well.

### Quick start

```bash
# 1. install (Node.js 22.12+)
sudo apt install -y bubblewrap socat ripgrep util-linux
npm install -g @anthropic-ai/sandbox-runtime@0.0.78

# 2. enable: answer "y" to "Enable sandbox" in `t4g init`,
#    or set `enabled = true` under [sandbox] in config.toml

# 3. check and restart
t4g doctor            # checks srt, bwrap, socat, rg, script and runs a smoke test through srt
t4g daemon restart
```

If the sandbox is enabled and a tool is missing, the daemon refuses to start, writes `[SANDBOX UNAVAILABLE]` with the install command into the Notion Input block, and logs the same message. With `enabled = false` none of these tools are needed. `srt_path` points at a specific `srt` binary; empty means `srt` on `PATH`.

### Filesystem

srt denies writes by default and allows reads by default.

| Setting | Effect |
| --- | --- |
| `read_only = false`, `workspace = false` | Whole host readable and writable (`allowWrite = ["/"]`), except srt's protected files. |
| `read_only = true`, `workspace = false` | Whole host readable, nothing writable except `allow_write` entries. |
| `read_only = false`, `workspace = true` | `/home`, `/root`, `/mnt` and `/media` are hidden; only `workspace_path` is visible and writable. The shell starts in `workspace_path`. |
| `read_only = true`, `workspace = true` | Same, but the workspace is read-only too. |
| `allow_read` | Paths kept readable inside hidden areas, e.g. `~/.nvm` or `~/.local/bin` for tools installed under the home directory in workspace mode. srt's own package is always kept readable. |
| `allow_write` | Extra writable paths, e.g. `~/.cache`, `~/.npm`, `~/.local`. |
| `deny_write` | Paths kept read-only inside writable areas (wins over `allow_write`). |
| `deny_read` | Paths hidden from the shell. |

- Relative paths resolve against `workspace_path` in workspace mode, otherwise against `cwd`.
- On Linux, `allow_write`/`deny_write` take literal paths (no globs), and create/modify/delete are not distinguished.
- srt always blocks writes to shell rc files, `.gitconfig`, `.git/hooks`, `.git/config`, `.vscode/`, `.idea/` and similar files, even inside writable paths.
- Temporary files go to srt's writable `TMPDIR` (`/tmp/claude`).
- Filesystem rules are fixed when the shell starts; run `t4g daemon restart` after changing them.

### Network

- Only `allowed_domains` are reachable. `*.example.com` wildcards are allowed; a bare `*` is rejected by srt.
- `denied_domains` wins over `allowed_domains`.
- Blocked requests fail with `Connection blocked by network allowlist` (HTTP) or `CONNECT tunnel failed, response 403` (HTTPS).
- An empty list means no network at all.

### Credential masking

```toml
[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
mode = "mask"
inject_hosts = ["api.github.com"]

[[sandbox.credentials.files]]
path = ".env"
mode = "mask"
extract = '(?m)^(?:OPENAI_API_KEY|JWT_SECRET)=(\S+)$'
on_extract_no_match = "deny"
inject_hosts = ["api.openai.com"]
```

What the shell sees, and what reaches the server:

```text
$ echo $GITHUB_TOKEN
fake_value_f38d04a3-6216-492f-96b4-d49ba120db07

$ curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user
  → srt proxy replaces the sentinel → api.github.com receives the real token
```

- `mode = "mask"`: the value is replaced by a per-session `fake_value_<uuid>` sentinel. srt substitutes the real value only on requests to the credential's `inject_hosts`. If `inject_hosts` is omitted, srt defaults it to every `allowed_domains` host.
- `mode = "deny"`: the file is unreadable / the variable is unset. Use this when the credential must never be available to sandboxed commands or injected outbound.
- Current srt rejects `inject_hosts = []` for `mode = "mask"`. Terminal4GPTWeb rejects the same configuration instead of silently widening it to all allowed domains.
- `extract`: only capture group 1 of the regex is masked (exactly one group required) and the rest stays intact, e.g. just the password inside `DATABASE_URL`. Without `extract` the whole file or value is replaced.
- `on_extract_no_match`: `warn` (leave readable, fail-open), `deny` (hide, fail-closed) or `error` (refuse to start).
- `tls_terminate = true` is required for masking so substitution also works inside HTTPS requests; srt sets CA trust variables (`SSL_CERT_FILE`, …) in the sandbox. `allow_plaintext_inject = true` is the explicit opt-out and only injects into plain-HTTP requests.
- Only HTTP(S) traffic through the proxy is rewritten. SSH, database wire protocols and other raw TCP connections receive the fake value.

### Sandbox limitations

> [!IMPORTANT]
> The sandboxed shell has its own network namespace. A dev server started **inside** the sandboxed terminal listens on the sandbox's loopback and is **not reachable from the Playwright browser** (`:b goto http://localhost:…`), which runs outside the sandbox. For browser E2E against a local server, start that server outside the sandbox or disable the sandbox for that workflow.

- Network allowlist changes and filesystem changes both need `t4g daemon restart`.
- Masking only protects configured files and variables; it is not a secret scanner.
- Terminal4GPTWeb is currently tested against `@anthropic-ai/sandbox-runtime` **0.0.78**. srt is still in the 0.0.x line, so use this pinned version unless a newer version has been verified with this project.

---

## Configuration

Default:

```text
~/.config/t4g/config.toml
```

Example:

```toml
[notion]
token = "secret_xxx"
api_version = "2026-03-11"
page_id = "..."
terminal_block_id = "..."
input_block_id = "..."
page_url = "https://..."
parent_page_id = "..."
help_page_id = "..."
help_page_url = "https://..."
browser_status_block_id = "..."
browser_image_block_id = "..."
browser_vision_page_id = "..."
browser_vision_block_id = "..."
browser_vision_page_url = "https://..."

[terminal]
shell = "/bin/bash"
cwd = "/home/user"
user = "user"
host = "ubuntu"
input_prompt = ""
columns = 120
rows = 60
poll_interval = 1.2
refresh_interval = 1.5
health_check_interval = 10.0
show_cursor = true
source_bashrc = true

[sandbox]
enabled = true
srt_path = ""
read_only = false
workspace = true
workspace_path = "/home/user/project"
allow_read = ["~/.nvm"]
allow_write = ["~/.cache"]
deny_read = []
deny_write = [".git"]
allowed_domains = ["github.com", "*.githubusercontent.com", "pypi.org", "files.pythonhosted.org", "api.openai.com"]
denied_domains = []
tls_terminate = true
allow_plaintext_inject = false

[[sandbox.credentials.files]]
path = ".env"
mode = "mask"
extract = '(?m)^(?:OPENAI_API_KEY|JWT_SECRET)=(\S+)$'
on_extract_no_match = "deny"
mask_duplicates = false
inject_hosts = ["api.openai.com"]

[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
mode = "mask"
inject_hosts = ["api.github.com"]

[browser]
width = 1280
height = 720
headless = true
timeout_ms = 15000
settle_ms = 350
show_cursor_overlay = true
vision_enabled = true
vision_quality = 35
vision_max_base64_chars = 160000
```

`NOTION_TOKEN` overrides the token stored in the config.

The `[sandbox]` keys are explained in [PTY sandbox (srt)](#pty-sandbox-srt).

After config changes:

```bash
t4g daemon restart
```

---

## Diagnostics

```bash
t4g doctor
```

Checks config, Linux / WSL environment, shell path, working directory, Notion page access, and both runtime blocks. With `sandbox.enabled = true` it also lists the effective sandbox mode, network allowlist and credential rules, checks `srt`, `bwrap`, `socat`, `rg` and `script`, and runs `true` through srt with the configured policy.

---

## Security model

Terminal4GPTWeb supports an optional PTY sandbox based on [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime), the same runtime behind Claude Code's sandbox.

```text
enabled = false
  → unrestricted PTY as the daemon user (srt not required)

enabled = true, read_only = false, workspace = false
  → host readable and writable, network limited to allowed_domains

enabled = true, read_only = true, workspace = false
  → read-only host view

enabled = true, workspace = true
  → user data hidden except workspace_path (read/write, or read-only with read_only = true)
```

With the sandbox on:

- writes are allowed only where configured, and srt always protects shell rc files, git hooks/config and editor config;
- outbound network is limited to `allowed_domains` through srt's proxy;
- configured credential files and environment variables are replaced by `fake_value_<uuid>` sentinels, and the real value is only sent to the credential's allowed hosts.

Masking is not a universal secret scanner: only configured files and variables are protected.

Recommended precautions:

- run the daemon as a dedicated non-root user;
- prefer `enabled = true` with workspace isolation for coding workflows;
- keep `allowed_domains` to what the work needs;
- protect known credential files and environment variables with mask or deny rules;
- never send sudo passwords or raw credentials through Notion Input;
- restrict access to the generated Notion page;
- treat Docker sockets or other privileged IPC endpoints as sandbox escapes if you expose them manually.

---

## Verification

The regression suite currently covers:

- Search Page / URL parent-page wizard paths;
- persistent PTY behavior and terminal controls;
- sandbox on/off launch paths and the missing-`srt` error;
- translation of read-only / workspace / allow-write / deny rules, network allowlists and credential rules into srt settings;
- Notion runtime block handling and browser control helpers.

GitHub Actions runs the test suite on Python 3.11, 3.12 and 3.13.

The sandbox path has been exercised end to end through `PTYSession → pty.fork() → srt → script → bash`: environment-variable and file masking, sentinel→real substitution on outbound HTTP requests, the network allowlist, deny-write, workspace isolation, Ctrl-C and terminal resize. On WSL2 Ubuntu (srt 0.0.78 installed through nvm) it was also driven through the Notion control page: HTTPS substitution with `tls_terminate` (the shell saw `fake_value_…`, the server received the real value), blocked HTTPS to a non-allowed domain, workspace isolation and resize. Browser smoke testing has been verified through Notion with Playwright and the Vision payload observation ID.

Destructive recovery cases such as deleting the live production control page are covered by automated tests rather than repeatedly deleting the active user page during routine regression runs.

---

## Limitations

Notion is not a low-latency terminal transport. Terminal semantics are preserved, but every interaction still passes through the Notion API.

Currently not supported as a native Notion terminal experience:

- terminal mouse reporting (Playwright browser mouse control is supported)
- sixel / kitty graphics
- pixel graphics
- terminal color styling
- clipboard escape sequences
- sub-second keystroke streaming
- multiple simultaneous PTY sessions
- automatic startup after WSL / Windows restart
- reaching a server started inside the srt sandbox from the Playwright browser (see [Sandbox limitations](#sandbox-limitations))

---

## Development

```bash
pip install -e . pytest
pytest
python -m compileall -q terminal4gptweb tests
```

GitHub Actions tests Python 3.11, 3.12, and 3.13.

---

## License

MIT
