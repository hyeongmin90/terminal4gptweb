# Terminal4GPTWeb GPT Bootstrap Prompt

[한국어](./GPT_PROMPT.ko.md) · [Main README](./README.en.md) · [Control Command Reference](./CONTROL_COMMANDS.md)

Paste the prompt below as the first message in a new ChatGPT Web conversation.

```text
In this conversation, use Terminal4GPTWeb as my local terminal and browser-control tool.

Through the Notion connection, find the "Terminal4GPTWeb" control page. Before doing any work, open and read its "Terminal4GPTWeb Help" child page, and treat the instructions there as the operating protocol for Terminal4GPTWeb in this conversation.

Operating rules:
- Observe Terminal or Browser Status before acting.
- Write exactly one action at a time to the Notion Input block.
- **Input runs only when the actual text ends with a newline.** Writing the command text without the final line break does not submit it. Preserve a trailing newline when using a Notion connector/API; for Markdown code-block edits, leave one blank line after the action before closing the code block. If a command remains visible in Input, check this first.
- One submission may be at most 4000 bytes (UTF-8). Larger input is not sent, and the Terminal shows `[Terminal4GPTWeb] Input not sent: ...`; split long content (e.g. files) into several `cat >> file <<'EOF'` submissions.
- After writing Input, wait for Input to reset and for the result to update before sending the next action.
- Do not combine ordinary text and control commands in one submission. For example, if text has been entered into a Codex/Claude Code TUI and a real Enter key is needed, submit the text first, then send a separate Input action containing only ":k ENTER".
- Terminal4GPTWeb control syntax such as ":k", ":c", ":s", ":rs", and ":b" is interpreted by the Notion Input protocol. Do not type those strings into the application/TUI chat field itself.
- For browser control, reason from the latest Browser Status and the Screenshot or Vision Payload with the same observation_id.
- move/click/drag must use the latest observation_id. After every browser action, wait for the next ready observation before continuing.
- If Browser Status is failed, inspect the error first and do not keep using coordinates from the previous screenshot.
- If Input shows [SANDBOX UNAVAILABLE], do not keep retrying commands; report the missing sandbox/SRT state.
- Never place passwords, API keys, SSH private keys, or other secrets directly into Notion Input.
- Do not ask me to manually copy terminal output or browser results back to you when the connected Notion page can be read directly.
- If unsure about a supported command, reread Terminal4GPTWeb Help or the control-command documentation instead of guessing.

When I ask you to inspect, modify, run, test, or debug a local project, continue as far as practical with:
observe → perform one action → observe the result → perform the next action.

If a GitHub connection is also available, use GitHub for repository code, issues, pull requests, and history, and use Terminal4GPTWeb for local execution, builds, tests, and TUI interaction.

Start now by finding the Terminal4GPTWeb control page and Terminal4GPTWeb Help page in Notion, reading Help, and then checking the current Terminal state. If I have not given you an actual task yet, stop after confirming that state and wait for my request.
```

## How to use it

1. Install Terminal4GPTWeb and start the daemon with `t4g daemon start`.
2. Connect Notion to ChatGPT Web and grant access to the workspace containing the Terminal4GPTWeb page.
3. Paste the prompt above as the first message in a new conversation.
4. Once GPT has read `Terminal4GPTWeb Help` and checked the current Terminal state, the session is ready.
5. Continue in the same conversation with normal task requests.

Examples:

```text
Find why the current project tests are failing and fix it.
```

```text
Start the server and verify the login page in the browser.
```

The bootstrap prompt intentionally does not duplicate the entire command syntax. The generated Notion `Terminal4GPTWeb Help` page and [CONTROL_COMMANDS.md](./CONTROL_COMMANDS.md) remain the source of truth for commands and detailed behavior.
