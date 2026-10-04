# Terminal4GPTWeb 제어 명령 전체 레퍼런스

[English](./CONTROL_COMMANDS.md) · [메인 README](./README.md)

이 문서는 Terminal4GPTWeb에서 사용할 수 있는 **모든 제어 명령**을 코드 기준으로 정리한 레퍼런스입니다.

범위:

- Notion **Input** 블록에서 실행하는 일반 shell 입력
- PTY 특수키 / Ctrl / raw byte 입력
- PTY resize
- Playwright browser 제어 명령
- Browser observation / Vision 사용 규칙
- 로컬 `t4g` CLI 명령

> [!IMPORTANT]
> `:k ENTER`, `:c C`, `:b ...` 같은 제어 명령은 **반드시 하나의 독립된 Terminal4GPTWeb Input action으로 제출**해야 합니다.
> 일반 문자열과 같은 Input에 이어 붙여 쓰는 문법이 아닙니다.
>
> 잘못된 예:
>
> ```text
> hello :k ENTER
> ```
>
> 올바른 예:
>
> ```text
> hello
>
> # 위 입력 처리 후, 다음 Input action에서
> :k ENTER
> ```
>
> 즉 Codex/Claude Code 같은 TUI에 문자열을 보낸 뒤 실제 Enter가 필요하면, 문자열 제출이 끝난 다음 `:k ENTER`를 **별도 action**으로 보냅니다.

---

## 1. Input 제출 규칙

Input 블록은 기본적으로 앞에 prompt 문자를 표시하지 않습니다.

일반 명령과 제어 명령은 **newline 하나로 끝나면 제출**됩니다. Notion UI에서는 명령 뒤 Enter를 한 번 누르면 됩니다.

예:

```text
pwd
```

daemon은 Input을 polling하기 때문에 newline이 없는 미완성 입력은 실행하지 않습니다. **Input에 명령이 보인다는 것만으로 제출된 것이 아닙니다.** 명령이 그대로 남아 있고 실행되지 않는다면 마지막 newline 누락을 먼저 확인합니다.

에이전트가 Notion API/connector로 Input을 수정하는 경우 실제 전송 text 끝에 newline 하나가 유지되도록 작성합니다. 실제 Input content 기준으로는 `pwd\n` 형태입니다. Markdown 코드블록 형태로 페이지를 수정하는 connector에서는 마지막 newline이 보존되도록 명령 뒤에 빈 줄 하나를 두고 코드블록을 닫는 것이 안전합니다.

예:

```markdown
```bash
pwd

```
```

위 표현은 Input 코드블록의 실제 내용이 newline으로 끝나도록 하기 위한 것입니다.

### 한 번에 하나의 action

한 Input 제출에는 하나의 shell command 또는 하나의 control action만 넣는 것을 권장합니다.

```text
observe
→ Input에 action 하나 작성
→ Input이 빈 블록으로 초기화될 때까지 대기
→ 결과 다시 확인
→ 다음 action
```

---

## 2. 일반 shell command

형식:

```text
<shell command>
```

예:

```text
pwd

git status

cd ~/project

python3
```

별도 shell을 매번 만드는 방식이 아니라 하나의 persistent PTY를 유지합니다.

따라서 다음 상태가 계속 유지됩니다.

- current working directory
- environment variables
- foreground process
- REPL
- TUI state
- shell history/process state

여러 줄 shell text를 제출하면 내부 newline은 Enter 입력으로 변환한 뒤 마지막에도 Enter를 추가합니다.

---

# PTY 제어 명령

## 3. 즉시 Ctrl token

다음 5개 token은 **newline 없이 즉시 처리**됩니다.

| Token | 전달되는 control | 일반 용도 |
| --- | --- | --- |
| `^C` | Ctrl-C | foreground process interrupt |
| `^D` | Ctrl-D | EOF |
| `^Z` | Ctrl-Z | suspend |
| `^L` | Ctrl-L | clear / redraw |
| `^\\` | Ctrl-\\ | quit signal |

예:

```text
^C
```

long-running command를 중단해야 할 때 single-newline submit을 기다리지 않도록 별도로 처리합니다.

---

## 4. `:ctrl` / `:c` — Ctrl 조합

형식:

```text
:ctrl <key>
:c <key>
```

예:

```text
:c C

:c O

:ctrl X

:ctrl BACKSLASH
```

지원 범위는 ASCII control character로 변환 가능한:

```text
@
A ... Z
[
\
]
^
_
```

입니다.

lowercase를 입력해도 uppercase로 정규화됩니다.

대표 예:

| 입력 | 결과 |
| --- | --- |
| `:c A` | Ctrl-A |
| `:c C` | Ctrl-C |
| `:c D` | Ctrl-D |
| `:c L` | Ctrl-L |
| `:c O` | Ctrl-O |
| `:c X` | Ctrl-X |
| `:c [` | ESC와 동일한 control byte |
| `:c BACKSLASH` | Ctrl-\\ |

TUI 예:

```text
# nano 저장
:c O

# nano 종료
:c X

# 실행 중단
:c C
```

---

## 5. `:key` / `:k` — PTY 특수키

형식:

```text
:key <name>
:k <name>
```

지원되는 canonical key:

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

지원 alias:

| Alias | 실제 key |
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

key name은 대소문자를 구분하지 않으며 underscore도 제거됩니다.

예:

```text
:k ENTER

:key UP

:k PGDN

:k ESC

:k F5
```

### TUI에서 Enter가 필요한 이유

Codex/Claude Code 같은 TUI는 pasted text와 실제 Enter key를 구분할 수 있습니다.

예를 들어 먼저 문자열을 하나의 Input action으로 보냅니다.

```text
질문 내용
```

문자열이 TUI 입력창에 들어갔지만 submit되지 않았다면, **같은 문자열 뒤에 `:k ENTER`를 붙이지 않습니다.**

다음 Input action에서 `:k ENTER`만 따로 보냅니다.

```text
:k ENTER
```

Terminal4GPTWeb이 이 두 제출을 각각 처리해서, 첫 번째는 문자열 입력으로 전달하고 두 번째는 실제 Enter key sequence로 전달합니다.

---

## 6. `:send` / `:s` — raw terminal input

형식:

```text
:send <text>
:s <text>
```

이 명령은 shell line을 실행하는 것이 아니라 디코딩된 byte/text를 **현재 foreground PTY에 그대로 전달**합니다.

지원 escape:

| 입력 | 전달 값 |
| --- | --- |
| `\n` | LF |
| `\r` | CR |
| `\t` | Tab |
| `\e` | ESC (`0x1b`) |
| `\\` | backslash |
| `\xNN` | 2자리 hex byte/character |

예:

```text
# vim 저장 후 종료
:s \e:wq\r

# vim 강제 종료
:s \e:q!\r

# ESC 전송
:s \e
```

일반 command 실행에는 `:send`보다 normal shell input을 사용하고, escape sequence나 TUI raw 입력이 필요한 경우에만 사용하는 것이 좋습니다.

알 수 없는 escape는 자동으로 삭제하지 않고 backslash를 보존하는 방향으로 처리됩니다.

---

## 7. `:resize` / `:rs` — PTY 크기 변경

형식:

```text
:resize <columns>x<rows>
:rs <columns>x<rows>
```

예:

```text
:rs 140x50

:resize 100x30
```

허용 범위:

```text
columns: 20 .. 400
rows:     5 .. 200
```

대문자 `X`도 허용되며 공백을 넣은 형태도 parser에서 처리됩니다.

예:

```text
:rs 120X40
:rs 120 x 40
```

resize 시:

- outer PTY size 변경
- pyte screen size 변경
- 실행 중인 shell/TUI에 SIGWINCH 전달
- SRT 사용 시 내부 `script` PTY에도 resize signal 전달

이 수행됩니다.

---

# Browser / Playwright 제어

## 8. `:browser` / `:b` — Browser command wrapper

형식:

```text
:browser <browser command>
:b <browser command>
```

예:

```text
:b goto https://example.com
```

현재 인식하는 browser subcommand 이름은 다음 11개이며, `open`이 `goto`의 alias이므로 실제 동작 종류는 10개입니다.

```text
goto
open
shot
save
full
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

`goto`와 `open`은 같은 navigation 동작입니다.

첫 browser command에서 Chromium이 lazy start되고 daemon이 종료/restart될 때까지 같은 browser context/page를 유지합니다.

따라서 action 사이에 다음 상태가 유지될 수 있습니다.

- cookie
- login state
- localStorage / sessionStorage
- focus
- browser history
- current page state

---

## 9. `:b goto <url>` / `:b open <url>`

페이지 이동.

형식:

```text
:b goto <url>
:b open <url>
```

예:

```text
:b goto https://example.com
```

동작:

1. Playwright `page.goto()`
2. `domcontentloaded`까지 대기
3. 설정된 `settle_ms` 대기
4. 새 screenshot/Vision/status observation 생성

navigation 후 mouse cursor 위치 기록은 초기화됩니다.

URL 인자는 하나만 받을 수 있습니다.

---

## 10. `:b shot`

현재 browser state를 변경하지 않고 새 observation을 만듭니다.

형식:

```text
:b shot
```

사용 시점:

- SPA가 action 뒤 늦게 render된 경우
- animation/load가 끝난 뒤 현재 화면을 다시 보고 싶은 경우
- 실패 이후 현재 page state를 다시 동기화하고 싶은 경우
- 최신 screenshot/Vision payload만 다시 만들고 싶은 경우

예:

```text
:b shot
```

---

## 10A. `:b save [label]` — 현재 화면 임시 저장

현재 최신 viewport screenshot을 **Browser Saved Snapshots** 영역에 복사해 둡니다. 이후 다른 URL로 이동하거나 화면이 바뀌어도 저장본은 남아 있어 여러 결과를 한 페이지에서 비교할 수 있습니다.

```text
:b save
:b save 검색 결과 A
```

- 먼저 `:b shot` 또는 다른 browser action으로 observation이 하나 있어야 합니다.
- label은 선택 사항입니다. 생략하면 현재 page title/URL을 사용합니다.
- live Browser Screenshot과 observation_id는 바뀌지 않습니다.
- 저장본은 임시 데이터이며 `:b clear-saved` 또는 daemon 재시작 시 삭제됩니다.

---

## 10B. `:b full [label]` — 긴 페이지를 tile로 저장

현재 document 전체를 full-page screenshot으로 캡처한 뒤 **현재 viewport 높이 단위 PNG 여러 장**으로 잘라 Browser Saved Snapshots에 저장합니다.

```text
:b full
:b full 긴 리포트
```

한 장의 세로로 매우 긴 이미지는 Notion에서 폭에 맞춰 축소되면서 글자와 UI가 지나치게 작아질 수 있습니다. `:b full`은 이 문제를 피하기 위해 예를 들어 1280×5000 페이지를 1280×720 정도의 여러 tile로 나누어 순서대로 보관합니다.

- 최대 20 tile까지 허용합니다.
- 20장을 넘는 페이지는 안전 제한으로 거부하며 필요한 구간을 scroll한 뒤 `:b save`로 선택 저장할 수 있습니다.
- full capture 뒤 현재 viewport를 다시 observation으로 게시하므로 새로운 observation_id를 사용해야 합니다.
- full-page tile은 비교/판독용입니다. tile 좌표를 click/move에 직접 사용하지 말고 live Browser Screenshot 좌표를 사용합니다.

---

## 10C. `:b clear-saved` — 임시 저장본 삭제

```text
:b clear-saved
```

Browser Saved Snapshots에 쌓인 viewport/full-page tile 이미지를 모두 제거합니다. live Browser Screenshot에는 영향을 주지 않습니다.

---

## 11. `:b move <observation_id> <x> <y>`

마우스를 지정 좌표로 이동합니다.

형식:

```text
:b move <observation_id> <x> <y>
```

예:

```text
:b move obs_20261002T040000Z_0003 620 240
```

용도:

- hover menu
- tooltip
- hover style 확인
- 클릭 전에 위치 확인

반드시 **현재 최신 observation_id**를 사용해야 합니다.

move 자체도 성공 후 새로운 observation을 생성하므로 hover 상태를 확인한 뒤 click할 때는 **move 이전 ID가 아니라 새 ID**를 사용합니다.

---

## 12. `:b click <observation_id> <x> <y>`

현재 viewport의 좌표를 클릭합니다.

형식:

```text
:b click <observation_id> <x> <y>
```

예:

```text
:b click obs_20261002T040000Z_0004 640 418
```

좌표는 **document 좌표가 아니라 viewport 기준 CSS pixel**입니다.

기본 viewport가 `1280x720`일 경우:

```text
왼쪽 위     = 0,0
오른쪽 아래 = 1280,720
```

설정 viewport 밖 좌표는 거부됩니다.

클릭 후:

- focus 변경
- navigation
- UI state 변경

등이 일어날 수 있으므로 새 observation을 확인한 뒤 다음 action을 결정해야 합니다.

---

## 13. `:b drag <observation_id> <x1> <y1> <x2> <y2>`

마우스 drag.

형식:

```text
:b drag <observation_id> <x1> <y1> <x2> <y2>
```

예:

```text
:b drag obs_20261002T040000Z_0005 200 300 700 300
```

내부 동작:

1. 시작 좌표로 move
2. mouse down
3. 목적지까지 8 step으로 move
4. mouse up

마지막 cursor 위치는 목적지 좌표로 기록됩니다.

사용 예:

- slider
- drag-and-drop
- canvas interaction
- selection handle

---

## 14. `:b scroll <dx> <dy>`

mouse wheel scroll.

형식:

```text
:b scroll <dx> <dy>
```

예:

```text
# 아래로
:b scroll 0 600

# 위로
:b scroll 0 -600

# 가로 scroll
:b scroll 400 0
```

`dx`, `dy`는 Playwright mouse wheel delta입니다.

- positive `dy`: 아래 방향
- negative `dy`: 위 방향

scroll은 observation_id를 인자로 받지 않지만 성공 후 새로운 observation을 만듭니다.

Browser Status의:

```text
scroll: x,y
```

는 현재 `window.scrollX`, `window.scrollY`입니다.

하지만 click/move/drag 좌표는 scroll과 무관하게 항상 **현재 viewport 기준**입니다.

---

## 15. `:b type <text>`

현재 keyboard focus를 가진 element에 literal text를 삽입합니다.

형식:

```text
:b type <text>
```

예:

```text
:b type user@example.com

:b type hello world
```

Playwright `keyboard.insert_text()`를 사용합니다.

중요:

- Enter를 자동으로 누르지 않습니다.
- shortcut key 해석을 하지 않습니다.
- 먼저 input/textarea/contenteditable에 focus가 있어야 합니다.

따라서 form 입력은 보통:

```text
click field
→ 새 observation 대기
→ type text
→ 새 observation 대기
→ key Tab 또는 key Enter
```

순서로 처리합니다.

---

## 16. `:b key <key>`

Playwright browser keyboard key press.

형식:

```text
:b key <key>
```

예:

```text
:b key Enter

:b key Tab

:b key Escape

:b key ArrowDown

:b key Shift+Tab

:b key Control+A
```

인자는 Playwright `keyboard.press()`에 그대로 전달됩니다.

따라서 PTY의 `:k ENTER` key table과 **다른 체계**입니다.

Browser key 예:

- `Enter`
- `Tab`
- `Escape`
- `Backspace`
- `Delete`
- `ArrowUp`
- `ArrowDown`
- `ArrowLeft`
- `ArrowRight`
- `Home`
- `End`
- `PageUp`
- `PageDown`
- modifier 조합: `Control+A`, `Shift+Tab` 등

한 번에 하나의 `key` argument만 받습니다. 공백이 포함된 문자열 입력은 `:b type`을 사용합니다.

---

## 17. `:b back`

browser history 뒤로 가기.

형식:

```text
:b back
```

동작 후 `domcontentloaded`까지 기다린 다음 observation을 생성합니다.

추가 인자는 허용되지 않습니다.

---

## 18. `:b reload`

현재 페이지 reload.

형식:

```text
:b reload
```

동작 후 `domcontentloaded`까지 기다린 다음 observation을 생성합니다.

추가 인자는 허용되지 않습니다.

---

# Browser observation 규칙

## 19. Browser Status

browser action 시작 시:

```text
status: running
command: ...
viewport: 1280x720
```

성공 시:

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

실패 시:

```text
status: failed
command: ...
error: ...
viewport: ...
```

다음 action은 가능한 한 `status: ready`를 확인한 뒤 실행합니다.

---

## 20. observation_id

모든 성공한 browser action은 새로운 observation ID를 만듭니다.

형식 예:

```text
obs_20261002T040000Z_0007
```

다음 3개 coordinate action은 최신 ID를 강제합니다.

- `move`
- `click`
- `drag`

오래된 ID를 사용하면:

```text
STALE_OBSERVATION
```

으로 실패합니다.

안전한 기본 루프:

```text
Browser Status ready 확인
→ observation_id 저장
→ 같은 ID의 screenshot/Vision 확인
→ action 하나 실행
→ 새 ready observation 대기
→ 이전 ID 폐기
→ 반복
```

---

## 21. Browser Screenshot

control page에 표시되는 최신 viewport PNG입니다.

특징:

- full page screenshot이 아님
- 현재 viewport만 캡처
- CSS pixel scale 사용
- coordinate 판단용 화면과 동일한 viewport 기준

off-screen content는 scroll한 뒤 새 screenshot을 확인해야 합니다.

---

## 22. Browser Vision Payload

별도 child page에 저장되는 GPT용 JPEG payload입니다.

형식:

```text
observation_id: obs_...
mime: image/jpeg
encoding: base64
viewport: 1280x720
quality: 35
data_base64:
...
```

사용 시 Browser Status의 observation_id와 Vision payload의 observation_id가 같은지 확인합니다.

JPEG quality는 설정값에서 시작해 payload가 너무 크면:

```text
configured quality
→ 25
→ 15
→ 8
```

순서로 낮춰서 `vision_max_base64_chars` 안에 맞추려고 합니다.

끝까지 맞지 않으면 browser action이 실패합니다.

---

## 23. cursor overlay

설정:

```toml
show_cursor_overlay = true
```

이면 마지막 mouse 위치를 screenshot에 작은 marker로 표시합니다.

적용되는 action:

- move
- click
- drag

navigation `goto/open` 시 cursor 기록은 초기화됩니다.

---

## 24. Browser 실패 복구

### STALE_OBSERVATION

원인:

- screenshot을 본 뒤 다른 action으로 화면이 갱신됨
- 이전 ID를 다시 사용함

처리:

```text
Browser Status 다시 읽기
→ 새 screenshot/Vision 확인
→ 새 observation_id로 좌표 재계산
```

### Coordinate outside viewport

예:

```text
Coordinate (1300, 400) is outside viewport 1280x720
```

처리:

- viewport 안 좌표 사용
- off-screen element라면 먼저 scroll

### async/SPAs

action 직후 `settle_ms`보다 늦게 화면이 변하면:

```text
:b shot
```

으로 새 observation만 다시 얻습니다.

### Playwright/Chromium 미설치

```bash
playwright install chromium
```

### Vision payload too large

- browser viewport 축소
- `vision_max_base64_chars` 조정

---

## 25. 현재 Browser control 범위

현재 Notion command surface는:

- 하나의 persistent Playwright browser context
- 하나의 controlled page
- viewport mouse
- keyboard
- screenshot
- Vision payload

를 제공합니다.

현재 command surface에 없는 기능:

- CSS selector 직접 click
- DOM query
- locator command
- popup/new tab 자동 switching
- file chooser/upload command
- download management
- browser forward
- 별도 browser close/restart command
- multiple controlled tabs

사이트가 새 tab/window를 열어도 자동으로 그 page가 controlled page가 되지는 않습니다.

---

# 로컬 t4g CLI

## 26. `t4g init`

초기 설정 wizard.

```bash
t4g init
t4g init --config /path/to/config.toml
```

설정하는 주요 항목:

- Notion token/page
- shell
- cwd
- terminal size
- SRT sandbox
- workspace/read-only/network
- Browser settings
- control/help page 생성

---

## 27. `t4g reinit`

Notion control page/runtime page를 다시 생성합니다.

```bash
t4g reinit
t4g reinit --config /path/to/config.toml
```

기존 로컬 terminal/browser 설정을 유지하면서 Notion page/block ID를 재생성할 때 사용합니다.

---

## 28. `t4g run`

foreground daemon 실행.

```bash
t4g run
t4g run --config /path/to/config.toml
```

터미널에서 직접 로그를 보며 디버깅할 때 적합합니다.

---

## 29. `t4g doctor`

설치/설정 진단.

```bash
t4g doctor
t4g doctor --config /path/to/config.toml
```

확인 항목에는 다음이 포함됩니다.

- config load
- Linux/WSL
- shell/cwd
- SRT dependency
- sandbox smoke test
- Playwright package
- Notion page/runtime block

---

## 30. `t4g daemon start`

background daemon 시작.

```bash
t4g daemon start
t4g daemon start --config /path/to/config.toml
```

---

## 31. `t4g daemon stop`

background daemon 종료.

```bash
t4g daemon stop
```

---

## 32. `t4g daemon restart`

daemon 재시작.

```bash
t4g daemon restart
t4g daemon restart --config /path/to/config.toml
```

config 변경 후 적용할 때 주로 사용합니다.

---

## 33. `t4g daemon status`

daemon 상태 확인.

```bash
t4g daemon status
t4g daemon status --config /path/to/config.toml
```

---

## 34. `t4g daemon logs`

daemon log 출력.

```bash
t4g daemon logs
```

기본 최근 100줄입니다.

줄 수 지정:

```bash
t4g daemon logs -n 300
t4g daemon logs --lines 300
```

follow:

```bash
t4g daemon logs -f
t4g daemon logs --follow
```

조합:

```bash
t4g daemon logs -n 300 -f
```

---

## 35. 공통 CLI

버전:

```bash
t4g --version
```

도움말:

```bash
t4g --help
t4g daemon --help
```

`init`, `reinit`, `run`, `doctor`, `daemon`은 config 경로를 지정할 수 있습니다.

```bash
--config /path/to/config.toml
```

기본 config:

```text
~/.config/t4g/config.toml
```

---

# 빠른 요약

## Input control

| 기능 | 명령 |
| --- | --- |
| shell line | `<command>` + blank line |
| Ctrl | `:ctrl KEY`, `:c KEY` |
| special key | `:key NAME`, `:k NAME` |
| raw input | `:send TEXT`, `:s TEXT` |
| resize | `:resize COLSxROWS`, `:rs COLSxROWS` |
| browser | `:browser ...`, `:b ...` |
| immediate Ctrl | `^C`, `^D`, `^Z`, `^L`, `^\\` |

## Browser subcommands

| 기능 | 명령 |
| --- | --- |
| 이동 | `:b goto <url>` / `:b open <url>` |
| 관찰 | `:b shot` |
| 현재 화면 임시 저장 | `:b save [label]` |
| 긴 페이지 tile 저장 | `:b full [label]` |
| 임시 저장본 삭제 | `:b clear-saved` |
| move/hover | `:b move <obs> <x> <y>` |
| click | `:b click <obs> <x> <y>` |
| drag | `:b drag <obs> <x1> <y1> <x2> <y2>` |
| scroll | `:b scroll <dx> <dy>` |
| text | `:b type <text>` |
| key | `:b key <key>` |
| back | `:b back` |
| reload | `:b reload` |
