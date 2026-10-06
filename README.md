# Terminal4GPTWeb

[English](./README.en.md) · [GPT 시작 프롬프트](./GPT_PROMPT.ko.md) · [제어 명령 전체 레퍼런스](./CONTROL_COMMANDS.ko.md) · [상세 설치 가이드](./INSTALL.ko.md)

**웹 기반 AI 에이전트에 실제 개발 환경의 터미널과 브라우저를 연결합니다. 셸 서버를 인터넷에 직접 노출할 필요는 없습니다.**

`Terminal4GPTWeb`은 Notion을 **웹 AI 클라이언트와 로컬 Linux PTY / Playwright 실행 환경 사이의 제어 브리지**로 사용합니다.

GitHub·Notion 같은 SaaS 커넥터가 코드와 문서의 **컨텍스트**를 제공한다면, Terminal4GPTWeb은 그 컨텍스트를 바탕으로 실제 머신에서 **실행하고 검증하는 계층**을 제공합니다.

웹 AI가 생성된 Notion 페이지를 읽고 수정할 수 있다면 다음과 같은 작업이 가능합니다.

- `git`, build, unit/integration test 같은 실제 셸 명령 실행
- Docker, Kubernetes, SSH, cloud CLI 등 로컬에 설치된 도구 사용
- 현재 터미널 화면 읽기와 persistent PTY 상태 유지
- Enter, 방향키, Ctrl-C 등 실제 키 입력과 TUI 프로그램 조작
- `nano`, `vim`, `less`, `top`, Codex 같은 터미널 애플리케이션 사용
- Playwright로 웹 페이지를 열고 화면을 확인한 뒤 브라우저 E2E 검증
- 선택적으로 [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime) 안에서 셸 실행 — 파일시스템·네트워크 제한과 credential masking

한 줄로 표현하면:

> **Web AI ↔ Notion ↔ Terminal4GPTWeb ↔ PTY / Playwright ↔ WSL / Linux / Web**

Notion은 제품의 목적지가 아니라, 여러 웹 AI가 접근할 수 있는 **transport / control surface**입니다. 실제 터미널과 브라우저 세션은 로컬 daemon이 관리합니다.

Terminal4GPTWeb은 특정 모델 제공자에 종속되지 않습니다. 생성된 Notion 페이지를 안정적으로 읽고 수정할 수 있는 웹 AI 클라이언트라면 같은 구조를 사용할 수 있으며, 현재 문서는 ChatGPT Web 흐름을 기준으로 가장 자세히 설명합니다.

> [!CAUTION]
> PTY sandbox는 **선택 기능**입니다. `sandbox.enabled = false`(기본값)이면 Input에 입력된 명령은 daemon을 실행한 Linux 사용자의 권한으로 그대로 실행됩니다. `sandbox.enabled = true`이면 셸이 [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime) 안에서 실행되어 파일시스템·네트워크·credential masking 규칙이 적용되지만, 일반적인 secret 관리까지 대체하지는 않습니다.

---

## 왜 만들었나요?

웹 AI의 GitHub·Notion 커넥터는 repository, issue, PR, 문서 같은 원격 컨텍스트를 읽고 쓰는 데 유용합니다. 하지만 그것만으로는 사용자의 실제 개발 환경에서 `npm test`, `pytest`, `kubectl`, `docker`, SSH, 로컬 서버, 브라우저 E2E 같은 작업을 직접 실행할 수 없습니다.

Terminal4GPTWeb은 이 **connector와 runtime 사이의 빈 공간**을 채웁니다.

1. 웹 AI가 **Terminal** 블록을 읽습니다.
2. 웹 AI가 **Input** 블록에 명령 또는 키 입력을 작성합니다.
3. `t4g` daemon이 이를 읽어 실제 PTY로 전달합니다.
4. PTY 화면을 다시 **Terminal** 블록에 렌더링합니다.
5. 웹 AI가 갱신된 화면을 읽고 다음 작업을 이어갑니다.
6. 필요하면 같은 흐름으로 Playwright 브라우저를 조작하고 결과 화면까지 검증합니다.

즉, SaaS 커넥터를 대체하려는 도구가 아니라 **커넥터가 확보한 컨텍스트를 실제 환경에서 실행·검증으로 이어 주는 도구**입니다.

별도의 공개 SSH endpoint, 자체 웹 서버, DB, MQ가 필요하지 않습니다.

---

## 구조

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
                         │ srt (선택)                │
                         │  bubblewrap fs rules      │
                         │  network allowlist proxy  │
                         │  credential masking       │
                         └────────────┬──────────────┘
                                      │
                                      ▼
                              Bash / TUI on WSL / Linux
```

Terminal 블록은 stdout을 계속 쌓는 로그가 아니라 **현재 터미널 화면의 snapshot**입니다.

ANSI cursor 이동, 화면 지우기, scrolling, redraw sequence를 로컬에서 `pyte`로 처리한 뒤 최종 화면만 Notion에 기록합니다.

그래서 `top`, `less`, `vim`, Codex처럼 화면을 다시 그리는 프로그램도 텍스트 TUI 수준에서 사용할 수 있습니다.

---

## 주요 기능

- Persistent interactive Bash
- 실제 PTY 기반 동작
- ANSI / VT screen emulation
- `cd`, 환경변수, REPL 상태 유지
- foreground process stdin 전달
- Ctrl-C / Ctrl-D / Ctrl-Z / Ctrl-L / Ctrl-\\
- 방향키, Home/End, Page Up/Down
- Enter, Backspace, Delete, Insert, Tab, Esc
- F1-F12
- raw byte / escape sequence 입력
- runtime terminal resize
- persistent Playwright Chromium session
- Notion Browser Screenshot 자동 갱신
- 별도 child page의 압축 JPEG Vision payload
- observation ID 기반 mouse move/click/drag/scroll
- browser keyboard / navigation 제어
- background daemon
- single-instance lock
- runtime block 자동 복구
- `doctor` 진단
- 선택적 srt PTY sandbox: read-only / workspace 파일시스템 격리, 쓰기 허용·차단 목록, 외부 도메인 허용 목록
- Claude Code 방식의 credential masking (파일·환경변수): 셸에서는 `fake_value_<uuid>`로 보이고, 허용된 HTTPS 요청에는 실제 값이 실림

현재 Bash, Python REPL, nano, vim 스타일 key sequence, Codex TUI, interactive prompt, long-running process + Ctrl-C 형태를 실제로 테스트했습니다.

---

## 요구사항

- WSL2 Ubuntu 또는 Linux
- Python 3.11+
- Bash
- Notion API token: Personal Access Token 또는 Internal Connection token
- 생성 페이지의 부모로 사용할 Notion page
- 웹 AI에서 원격 제어하려면 생성된 페이지를 읽고 수정할 수 있는 **Notion 연결이 필수**
- ChatGPT Web은 현재 문서에서 가장 자세히 설명하는 기준 클라이언트
- 개발 워크플로에는 해당 AI 클라이언트의 **GitHub 연결 권장**
- 반복 운영 점검에는 지원되는 경우 ChatGPT 일정/자동화 기능 사용 가능
- sandbox 사용 시에만: Node.js 22.12+, [`@anthropic-ai/sandbox-runtime`](https://github.com/anthropic-experimental/sandbox-runtime) **0.0.78** (`srt`, 현재 검증 버전), `bubblewrap`, `socat`, `ripgrep`, `script`(util-linux)

> [!IMPORTANT]
> Terminal4GPTWeb 자체가 별도의 GPT API를 제공하는 구조는 아닙니다. GPT 웹은 생성된 Notion 페이지를 읽고 수정하는 방식으로 로컬 runtime에 접근하므로 GPT 웹에서 사용할 때는 Notion 연결이 필요합니다.

---

## 처음 설치하는 경우

처음부터 설치한다면 **[INSTALL.ko.md](./INSTALL.ko.md)**를 먼저 보는 것을 권장합니다. Notion Developer portal에서 token을 만드는 과정부터 Parent Page 권한, Linux 패키지, Playwright, wizard, sandbox config, ChatGPT Notion 연결, 첫 smoke test까지 순서대로 설명합니다.

아래는 전체 과정을 압축한 버전입니다.

### 1. Notion Parent Page 준비

Notion에 빈 페이지를 하나 만듭니다.

```text
Terminal4GPTWeb Root
```

현재 `t4g init`은 생성 페이지를 넣을 parent page를 하나 선택합니다. URL을 미리 복사하지 않아도 wizard에서 page 검색으로 선택할 수 있습니다.

### 2. Notion API Token 준비

**로컬 t4g daemon**이 Notion API를 호출하기 위한 token입니다. **ChatGPT 웹의 Notion 연결과는 별개**입니다.

사용 가능한 방식:

- 개인 신뢰 환경: **Personal Access Token (PAT)**
- 전용 bot 권한 분리: **Internal Connection token**

Internal Connection을 쓴다면 Parent Page 접근 권한을 부여하고 page content를 읽고/추가하고/수정할 수 있는 capability가 필요합니다.

Notion 공식 문서:

- https://developers.notion.com/guides/get-started/quick-start
- https://developers.notion.com/guides/get-started/internal-connections

#### Notion API rate limit과 polling

Notion API에는 **connection 단위 제한**과 **workspace 전체 공유 제한**이 있습니다. 현재 공식 문서 기준 connection 제한은 다음과 같습니다.

| Workspace plan | Connection limit |
| --- | ---: |
| Business / Enterprise | 600 requests/minute (평균 10 req/s) |
| 그 외 plan | 180 requests/minute (평균 3 req/s) |

workspace 공유 한도와 일부 endpoint별 별도 제한도 있으므로, 같은 workspace에서 다른 integration이 많은 요청을 보내면 t4g 자체 요청량이 낮아도 429가 발생할 수 있습니다. 제한 수치는 변경될 수 있으므로 최신 값은 [Notion Request limits](https://developers.notion.com/reference/request-limits)를 기준으로 확인하세요.

Terminal4GPTWeb은 기본 설정에서 API 요청이 terminal 수에 비례해 무제한으로 늘어나지 않도록 제어합니다.

- Input GET polling은 terminal을 **round-robin**으로 한 개씩 조회합니다.
- polling slot은 최소 0.6초라서 routine Input polling 자체는 전체 합계 약 **1.67 req/s 이하**로 제한됩니다.
- terminal 수가 늘어나면 각 terminal의 실제 polling 간격이 늘어납니다. 예: 기본 `poll_interval = 1.2`에서 1개는 1.2초, 2개는 1.2초, 3개는 약 1.8초, 8개는 약 4.8초 간격입니다.
- runtime health check도 terminal별로 분산 실행하며, Browser health check는 첫 terminal 주기에만 수행합니다.
- 화면 갱신, Browser/Vision 작업, block 복구 등은 추가 API 요청을 만들 수 있으므로 위 수치는 전체 API 사용량의 절대 상한은 아닙니다.

Notion이 429 또는 529를 반환하면 t4g는 `Retry-After`를 존중해 제한된 횟수만 재시도합니다. GET/DELETE 같은 idempotent 요청은 일시적인 5xx에도 backoff 후 재시도할 수 있지만, POST/PATCH 쓰기 요청은 애매한 일시적 5xx에서 자동 재시도하지 않습니다. 특히 503은 응답만 실패하고 쓰기는 이미 반영되었을 수 있습니다. 이는 동일 block 생성/수정을 중복 적용하지 않기 위한 동작입니다.

### 3. 설치

```bash
git clone https://github.com/hyeongmin90/terminal4gptweb.git
cd terminal4gptweb

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
playwright install chromium
```

PTY sandbox를 켤 경우에만 (Ubuntu/WSL2, Node.js 22.12+):

```bash
sudo apt install -y bubblewrap socat ripgrep util-linux
npm install -g @anthropic-ai/sandbox-runtime@0.0.78
srt --version
```

`sandbox.enabled = true`가 아니면 위 도구는 필요 없습니다.

설치 확인:

```bash
t4g --version
t4g --help
```

프로젝트 폴더 이름이나 위치를 변경해서 editable install이 깨졌다면:

```bash
cd ~/terminal4gptweb
pip install -e .
hash -r
```

### 4. Wizard 실행

```bash
t4g init
```

Notion API token을 입력한 뒤 Parent Page를:

```text
Choose parent Notion page

  1. Search pages
  2. Enter URL / page ID
```

에서 선택합니다.

이어 shell, initial working directory, terminal 크기, srt PTY sandbox 사용 여부(및 파일시스템·네트워크 옵션) 등을 설정합니다.

생성 구조:

```text
Parent Page
└─ Terminal4GPTWeb
   ├─ Terminal / Input / Browser
   ├─ Terminal4GPTWeb Help
   └─ Browser Vision Payload
```

설정 파일:

```text
~/.config/t4g/config.toml
```

### 5. 진단 및 실행

```bash
t4g doctor
t4g daemon start
t4g daemon status
```

### 6. ChatGPT 웹에서 Notion 연결

이것은 위의 **로컬 Notion API token과 별개의 두 번째 연결**입니다.

ChatGPT의 Apps/Plugins에서 Notion을 연결하고, Terminal4GPTWeb 페이지가 있는 계정/workspace/content에 접근할 수 있도록 승인합니다.

OpenAI 도움말:

https://help.openai.com/ko-kr/articles/12532955-notion-app-and-setup-in-chatgpt

### 7. 첫 동작 확인

Notion Input:

```text
pwd
```

명령 뒤 Enter를 한 번 눌러 제출합니다.

Terminal이 갱신되고 Input이 빈 블록으로 초기화되면 정상입니다.

Browser:

```text
:b goto https://example.com
```

Browser Status와 Screenshot이 갱신되는지 확인합니다.

메인 페이지 전체를 삭제했다면:

```bash
t4g reinit
t4g daemon restart
```

---

## 처음 GPT에 연결할 때

새 ChatGPT Web 대화에서 처음 Terminal4GPTWeb을 사용할 때는 **[GPT 시작 프롬프트](./GPT_PROMPT.ko.md)**를 첫 메시지로 붙여 넣는 것을 권장합니다.

이 프롬프트는 GPT에게 Notion의 `Terminal4GPTWeb Help`를 먼저 읽게 하고, 이후 Terminal/Input/Browser를 올바른 `observe → act → observe` 방식으로 사용하도록 안내합니다. 전체 command 문법을 프롬프트에 복제하지 않고 Help 페이지와 [제어 명령 전체 레퍼런스](./CONTROL_COMMANDS.ko.md)를 source of truth로 사용합니다.

---

## 웹 AI 연결 구성 (ChatGPT 기준)

Terminal4GPTWeb은 특정 웹 AI에 고정되지 않지만, 아래는 현재 가장 자세히 검증·문서화한 **ChatGPT Web 기준 구성**입니다. 다른 웹 AI도 생성된 Notion 페이지를 읽고 수정할 수 있다면 같은 제어 흐름을 사용할 수 있습니다.

### 1. Notion — 필수

ChatGPT에 Notion을 연결하고 생성된 Terminal4GPTWeb 페이지를 ChatGPT가 읽고 수정할 수 있게 해야 합니다.

GPT 웹이 로컬 runtime에 접근하는 경로는 다음과 같습니다.

```text
GPT Web
  ↓ Notion 읽기/수정
Terminal4GPTWeb 제어 페이지
  ↓ local daemon polling
PTY / Playwright
```

Notion 연결이 없더라도 로컬 daemon 자체는 실행할 수 있지만, GPT 웹에서 이 페이지를 터미널/브라우저 도구처럼 사용할 수는 없습니다.

### 2. GitHub — 개발 작업에 권장

ChatGPT에 GitHub도 연결하면 repository context와 로컬 실행 환경을 함께 사용할 수 있습니다.

권장 개발 흐름:

```text
GitHub
  ↓ issue / PR / commit history / code context
GPT Web
  ↓
Notion → Terminal4GPTWeb
  ↓
로컬 수정 / build / unit test / integration test
  ↓
Playwright + Vision
  ↓
브라우저 E2E 검증
```

GitHub에서는 코드, 이슈, PR, 변경 이력을 확인하고, 실제 머신에서 실행해야 하는 build/test 명령은 Terminal4GPTWeb을 통해 수행하는 식입니다.

예:

```text
이 저장소 최신 변경사항을 리뷰하고 관련 테스트를 로컬에서 실행한 뒤
Playwright로 실제 웹 화면까지 검증해줘.

연결된 이슈를 확인하고 로컬에서 재현한 뒤 수정하고,
테스트를 통과시키고 Browser Vision으로 영향받은 화면까지 확인해줘.
```

### 3. 일정 / 자동화 — OPS에 선택적으로 활용

사용 중인 ChatGPT 환경에서 일정/자동화 기능을 지원한다면 Terminal4GPTWeb을 반복 운영 점검 surface로 사용할 수도 있습니다.

예를 들어 주기적으로 다음을 확인하게 할 수 있습니다.

- `docker ps`, process/service 상태
- 로컬 health endpoint
- 최근 ERROR 로그
- disk / memory 상태
- Playwright 기반 간단한 브라우저 smoke test
- 이상이 있을 때만 알림

예시:

```text
매일 아침 Terminal4GPTWeb 페이지를 확인해.
서비스 health checklist와 최근 오류 로그를 확인하고,
Playwright로 메인 화면 smoke test까지 실행해.
문제가 있을 때만 알려줘.
```

반복 점검은 가능한 한 read-only 명령 위주로 구성하는 것을 권장합니다. 비밀번호, API Key, private key 같은 비밀정보를 Notion Input에 넣으면 안 됩니다.

---

## 웹 AI / 에이전트 동작 규칙

안정적으로 사용하려면 에이전트가 다음 `observe → act → observe` 규칙을 따르는 것이 좋습니다.

1. 먼저 **Terminal** 또는 **Browser Status**를 읽습니다.
2. **Input**에는 한 번에 하나의 명령/action만 작성합니다.
3. Input이 다시 빈 블록으로 초기화될 때까지 기다립니다.
4. 다음 action 전에 갱신된 Terminal/Browser Status를 다시 읽습니다.
5. 브라우저 좌표 action은 반드시 최신 `observation_id`를 사용합니다.
6. Vision이 필요하면 `vision_page_url`을 읽고 `data_base64`를 JPEG로 해석한 뒤 observation ID가 일치하는지 확인합니다.
7. Browser Status가 `failed`라면 이전 좌표를 계속 쓰지 말고 오류를 먼저 처리합니다.
8. **Input 실제 텍스트는 newline으로 끝나야 실행됩니다.** 명령 문자열만 적고 마지막 줄바꿈이 없으면 daemon은 미완성 입력으로 보고 실행하지 않습니다. Notion UI에서는 명령 뒤 Enter를 한 번 누릅니다. API/커넥터에서는 실제 Input text 끝에 `\n`이 남도록 작성하고, Markdown 코드블록 형태로 수정하는 커넥터라면 명령 뒤에 빈 줄 하나를 둔 뒤 코드블록을 닫습니다. 명령이 실행되지 않고 Input에 그대로 남아 있다면 trailing newline 누락을 가장 먼저 확인합니다.
9. Input에 `[SANDBOX UNAVAILABLE]`이 보이면 sandbox가 켜져 있는데 srt나 필요한 도구가 없는 상태입니다. 명령을 반복하지 말고 이 상태를 보고합니다.

이 규칙은 생성되는 **Terminal4GPTWeb Help** Notion child page에도 같이 기록됩니다.

---

## 활용 예시

### 개발 + 테스트

```text
GitHub context 확인
→ 코드 / 이슈 / PR 분석
→ Terminal에서 로컬 build/test
→ 애플리케이션 실행
→ Playwright로 접속
→ Vision으로 화면 확인
→ 실제 상호작용 후 결과 검증
```

### 로컬 장애 대응

```text
Terminal 확인
→ process/container 상태 확인
→ 로그 확인
→ health request
→ 수정/재시작
→ 다시 검증
```

### Browser E2E

```text
:b goto <url>
→ 최신 Vision payload 확인
→ 좌표 판단
→ :b click <obs_id> <x> <y>
→ 새 observation 대기
→ 변경된 화면 확인
```

### OPS / 정기 점검

고정 checklist를 짧게 두는 방식이 좋습니다.

```text
1. process/container 상태
2. health endpoint
3. 최근 ERROR 로그
4. disk + memory
5. browser smoke test
```

자동화한다면 매번 정상 보고를 보내기보다는 실제 조치가 필요한 실패가 있을 때만 알리도록 구성하는 편이 좋습니다.

---

## 백그라운드 실행

일반적으로는 daemon 모드를 권장합니다.

```bash
t4g daemon start
```

관리 명령:

```bash
t4g daemon status
t4g daemon restart
t4g daemon stop
t4g daemon logs
t4g daemon logs -f
```

runtime 파일:

```text
~/.cache/notion_is_terminal/daemon.pid
~/.cache/notion_is_terminal/daemon.log
~/.cache/notion_is_terminal/instance.lock
```

WSL 터미널 창을 닫아도 daemon은 계속 실행됩니다.

### systemd user service로 자동 시작

WSL 또는 일반 Linux에서 systemd를 사용한다면 저장소에 포함된 user unit으로 로그인/WSL 시작 시 Terminal4GPTWeb을 자동 실행할 수 있습니다.

기본 unit은 README의 설치 절차대로 저장소가 `~/terminal4gptweb`, 가상환경이 `.venv`에 있다고 가정합니다.

```bash
mkdir -p ~/.config/systemd/user
cp contrib/systemd/terminal4gptweb.service ~/.config/systemd/user/

# detached daemon이 이미 실행 중이면 먼저 중지
t4g daemon stop

systemctl --user daemon-reload
systemctl --user enable --now terminal4gptweb
systemctl --user status terminal4gptweb
```

다른 경로에 설치했다면 `~/.config/systemd/user/terminal4gptweb.service`의 `ExecStart`를 실제 `t4g` 경로로 수정합니다.

```bash
which t4g
```

로그는 systemd journal에서 확인합니다.

```bash
journalctl --user -u terminal4gptweb
journalctl --user -u terminal4gptweb -f
```

sandbox를 사용하고 `srt`를 nvm 같은 사용자 전용 PATH에 설치했다면, 대화형 셸에서는 보이지만 systemd user service에서는 찾지 못할 수 있습니다. 이 경우 `which srt`로 실제 경로를 확인해 `config.toml`의 `sandbox.srt_path`에 절대 경로를 지정합니다.

이 방식은 WSL 전용이 아니라 systemd를 사용하는 일반 Linux에서도 동일하게 동작합니다. WSL에서는 **WSL 인스턴스가 시작될 때** user service가 올라오는 것이며, Windows 부팅만으로 WSL 자체를 시작시키는 기능은 포함하지 않습니다.

일반 Linux 서버에서 로그인하지 않은 상태에서도 부팅 직후 user service를 실행해야 한다면 필요에 따라 linger를 활성화할 수 있습니다.

```bash
loginctl enable-linger "$USER"
```

디버깅할 때는 foreground 실행도 가능합니다.

```bash
t4g run
```

---

## 웹 AI에서 사용하기

생성된 Notion 페이지를 웹 AI가 Notion 커넥터를 통해 읽고 수정할 수 있다면, 이 페이지가 사실상 **웹 AI용 터미널·브라우저 실행 인터페이스**가 됩니다.

예를 들면:

```text
사용자:
Terminal4GPTWeb 페이지 확인해서 git status 실행해줘.

GPT:
1. Terminal 블록 확인
2. Input 블록에 "git status" 작성
3. daemon이 명령 실행
4. Terminal 블록 갱신
5. 결과를 다시 읽고 설명
```

실제 PTY 세션이 계속 유지되므로 GPT는 다음과 같은 흐름도 이어서 사용할 수 있습니다.

```bash
cd ~/project
git status
python3
codex
nano notes.txt
```

명령마다 새로운 shell을 만드는 구조가 아닙니다.

## 제어 명령

전체 제어 프로토콜은 별도 문서에 모아두었습니다.

- **[제어 명령 전체 레퍼런스](./CONTROL_COMMANDS.ko.md)** — Input 명령, PTY key/alias, Ctrl 입력, raw escape, resize 규칙, Playwright browser 명령, observation 규칙, 로컬 `t4g` CLI까지 전부 설명합니다.
- [English Control Command Reference](./CONTROL_COMMANDS.md)

기본 제어 흐름은 다음처럼 단순하게 유지합니다.

```text
현재 Terminal / Browser Status 관찰
→ Input에 action 하나 작성
→ Input 초기화 대기
→ 새 상태 관찰
→ 다음 action
```

예:

```text
git status

:k ENTER

:c C

:b goto https://example.com

:b shot
```

`:k ENTER` 같은 제어 명령은 일반 문자열 뒤에 붙이는 문법이 아니라 **하나의 독립된 Input action**입니다. 예를 들어 Codex에 문자열을 보낸 뒤 Enter가 필요하면 문자열 제출이 끝난 다음 `:k ENTER`만 별도로 제출합니다.

PTY는 지속형이므로 cwd, 환경변수, REPL, TUI 상태가 action 사이에 유지됩니다.

### Browser + Vision 개요

daemon은 하나의 persistent Playwright Chromium context/page도 유지합니다. cookie, 로그인 상태, local/session storage, focus, browser history 등이 browser action 사이에 유지될 수 있습니다.

각 정상 browser action은 새로운 observation을 게시합니다.

```text
Browser Status
  status / observation_id / url / title
  viewport / scroll / cursor
  vision_page_url

Browser Screenshot
  최신 viewport PNG

Browser Saved Snapshots
  비교용 viewport / full-width long screenshot

Browser Vision Payload
  압축 JPEG + 동일 observation_id
```

좌표 action은 최신 `observation_id`를 요구하므로 화면이 바뀐 뒤 이전 screenshot 좌표를 잘못 적용하는 것을 막습니다.

여러 페이지 결과를 비교해야 할 때는 이동하기 전에 `:b save [label]`로 현재 viewport를 **Browser Saved Snapshots**에 임시 보관할 수 있습니다. 세로로 긴 페이지는 `:b full [label]`로 **가로를 viewport 폭에 맞춘 한 장짜리 전체 세로 이미지**를 저장합니다. PNG/JPEG 같은 이미지를 브라우저에서 직접 연 경우에는 Chrome image viewer를 캡처하지 않고 이미지의 natural pixel을 직접 추출하므로 fit-to-height로 생기는 좌우 여백이 포함되지 않습니다. 필요할 때만 `:b full-tiles [label]`로 기존 tile 방식을 사용할 수 있습니다. 저장본은 `:b clear-saved` 또는 daemon 재시작 시 정리됩니다. live **Browser Screenshot**은 좌표 정확성을 위해 기존처럼 viewport 한 장만 유지합니다.

Browser 명령의 전체 문법, 좌표 규칙, focus/keyboard 동작, hover 흐름, 실패 복구, 현재 제한사항은 **[CONTROL_COMMANDS.ko.md](./CONTROL_COMMANDS.ko.md)**에 정리했습니다.

---

## Runtime block 자동 복구

Notion page ID는 고정 anchor로 보고, Terminal/Input code block ID는 교체 가능한 runtime reference로 관리합니다.

`health_check_interval`마다 Terminal과 Input을 각각 독립적으로 검사합니다.

한쪽 블록만 삭제되거나 trash로 이동하거나 잘못된 위치로 이동한 경우:

1. 정상 블록은 그대로 유지합니다.
2. 문제가 있는 블록만 다시 생성합니다.
3. 원래 Terminal/Input section 위치에 다시 삽입합니다.
4. 변경된 block ID만 `config.toml`에 반영합니다.

두 블록을 모두 삭제하면 둘 다 복구합니다.

Terminal/Input section 자체까지 삭제된 경우에는 원래 위치를 알 수 없으므로 페이지 하단에 새 runtime section을 생성하는 fallback을 사용합니다.

페이지 자체가 삭제되거나 접근 불가능한 경우에는 새 페이지를 임의 생성하지 않고 daemon을 중단합니다.

메인 제어 페이지 자체를 의도적으로 다시 만들려면:

```bash
t4g reinit
t4g daemon restart
```

`reinit`은 기존 로컬 terminal/browser 설정은 유지하고 Notion page와 runtime block ID만 새 값으로 교체합니다.

---

## PTY sandbox (srt)

기본적으로 셸은 daemon을 실행한 사용자 권한 그대로 동작합니다. `sandbox.enabled = true`로 설정하면 Claude Code의 sandbox Bash가 사용하는 런타임인 [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime) 안에서 셸을 실행합니다. t4g가 sandbox를 직접 구현하지 않고, `[sandbox]` 설정을 srt settings 파일로 변환한 뒤 srt를 통해 셸을 띄웁니다.

```text
sandbox.enabled = false   →  bash                                  (srt 불필요)
sandbox.enabled = true    →  srt -s ~/.cache/notion_is_terminal/srt-settings.json \
                               -- script -qfec "bash --rcfile … -i" /dev/null
```

srt가 적용하는 세 가지:

| 계층 | 동작 |
| --- | --- |
| 파일시스템 | bubblewrap mount: 허용한 경로 외 쓰기 차단, 지정한 경로 숨김 |
| 네트워크 | 셸을 별도 네트워크 namespace에서 실행. 모든 요청은 srt 프록시를 거치며 `allowed_domains`만 통과 |
| Credential | 설정한 파일·환경변수를 셸 안에서는 `fake_value_<uuid>`로 바꾸고, 허용된 host로 나가는 요청에서 프록시가 실제 값으로 치환 |

`script`가 srt 세션 안에서 셸에 제어 터미널을 제공하므로 job control과 Ctrl-C가 그대로 동작하고, 터미널 크기 변경(`:rs`)도 전달됩니다.

### 빠른 시작

```bash
# 1. 설치 (Node.js 22.12+)
sudo apt install -y bubblewrap socat ripgrep util-linux
npm install -g @anthropic-ai/sandbox-runtime@0.0.78

# 2. 켜기: `t4g init`의 "Enable sandbox"에 y로 답하거나,
#    config.toml의 [sandbox]에 enabled = true 설정

# 3. 확인 후 재시작
t4g doctor            # srt, bwrap, socat, rg, script 확인 + srt로 smoke test 실행
t4g daemon restart
```

sandbox를 켰는데 도구가 없으면 daemon이 시작을 거부하고, Notion Input 블록에 설치 명령이 담긴 `[SANDBOX UNAVAILABLE]` 메시지를 쓰며 로그에도 남깁니다. `enabled = false`이면 위 도구는 필요 없습니다. `srt_path`로 특정 `srt` 실행 파일을 지정할 수 있고, 비워두면 `PATH`에서 찾습니다.

### 파일시스템

srt는 쓰기를 기본 차단하고, 읽기는 기본 허용합니다.

| 설정 | 동작 |
| --- | --- |
| `read_only = false`, `workspace = false` | host 전체 읽기·쓰기 가능(`allowWrite = ["/"]`). 단, srt 보호 파일은 제외 |
| `read_only = true`, `workspace = false` | host 전체 읽기 가능, `allow_write` 외에는 쓰기 불가 |
| `read_only = false`, `workspace = true` | `/home`, `/root`, `/mnt`, `/media`를 숨기고 `workspace_path`만 보이며 쓰기 가능. 셸은 `workspace_path`에서 시작 |
| `read_only = true`, `workspace = true` | 위와 같되 workspace도 read-only |
| `allow_read` | 숨겨진 영역 안에서 읽기를 다시 허용할 경로. workspace 모드에서 홈 디렉터리 아래 설치한 도구(예: `~/.nvm`, `~/.local/bin`)를 쓸 때 지정. srt 자체 패키지는 자동으로 허용 |
| `allow_write` | 추가로 쓰기 허용할 경로. 예: `~/.cache`, `~/.npm`, `~/.local` |
| `deny_write` | 쓰기 가능한 영역 안에서 read-only로 둘 경로 (`allow_write`보다 우선) |
| `deny_read` | 셸에서 숨길 경로 |

- 상대 경로는 workspace 모드에서는 `workspace_path`, 그 외에는 `cwd` 기준입니다.
- Linux에서 `allow_write`/`deny_write`는 실제 경로만 받으며(glob 불가), 생성·수정·삭제를 구분하지 않습니다.
- srt는 쓰기 가능한 경로 안이라도 셸 rc 파일, `.gitconfig`, `.git/hooks`, `.git/config`, `.vscode/`, `.idea/` 등의 쓰기를 항상 막습니다.
- 임시 파일은 srt가 지정한 쓰기 가능한 `TMPDIR`(`/tmp/claude`)에 만들어집니다.
- 파일시스템 규칙은 셸 시작 시 고정되므로 변경 후 `t4g daemon restart`가 필요합니다.

### 네트워크

- `allowed_domains`에 있는 도메인만 접근할 수 있습니다. `*.example.com` 와일드카드는 가능하지만 `*` 단독은 srt가 거부합니다.
- `denied_domains`가 `allowed_domains`보다 우선합니다.
- 차단된 요청은 `Connection blocked by network allowlist`(HTTP) 또는 `CONNECT tunnel failed, response 403`(HTTPS)로 실패합니다.
- 목록이 비어 있으면 네트워크가 완전히 차단됩니다.

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

셸에서 보이는 값과 서버에 도착하는 값:

```text
$ echo $GITHUB_TOKEN
fake_value_f38d04a3-6216-492f-96b4-d49ba120db07

$ curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user
  → srt 프록시가 sentinel을 실제 값으로 치환 → api.github.com은 실제 토큰을 받음
```

- `mode = "mask"`: 값이 세션마다 새로 만든 `fake_value_<uuid>`로 바뀝니다. 실제 값은 해당 credential의 `inject_hosts`로 가는 요청에서만 치환됩니다. `inject_hosts`를 생략하면 srt가 모든 `allowed_domains`를 기본 범위로 사용합니다.
- `mode = "deny"`: 파일은 읽을 수 없고, 환경변수는 제거됩니다. credential을 sandbox에서 사용하거나 외부로 주입할 수 없게 하려면 이 모드를 사용합니다.
- 현재 srt는 `mode = "mask"`에서 `inject_hosts = []`를 거부합니다. Terminal4GPTWeb도 이를 설정 오류로 처리해 빈 배열이 의도치 않게 전체 허용으로 넓어지는 것을 막습니다.
- `extract`: 정규식의 capture group 1만 masking하고 나머지는 그대로 둡니다(정확히 하나의 group 필요). 예를 들어 `DATABASE_URL` 안의 비밀번호만 가릴 수 있습니다. `extract`가 없으면 파일이나 값 전체를 바꿉니다.
- `on_extract_no_match`: `warn`(그대로 노출, fail-open), `deny`(숨김, fail-closed), `error`(시작 거부)
- masking을 쓰려면 `tls_terminate = true`가 필요합니다. 그래야 HTTPS 요청 안에서도 치환되며, srt가 sandbox에 CA 신뢰 환경변수(`SSL_CERT_FILE` 등)를 설정합니다. `allow_plaintext_inject = true`는 이를 명시적으로 끄는 옵션으로, 평문 HTTP 요청에만 실제 값을 넣습니다.
- 프록시를 거치는 HTTP(S) 트래픽만 치환됩니다. SSH, DB 프로토콜 등 일반 TCP 연결에는 가짜 값이 그대로 전달됩니다.

### Sandbox 제약

> [!IMPORTANT]
> sandbox 셸은 별도 네트워크 namespace에서 실행됩니다. sandbox 터미널 **안에서** 띄운 개발 서버는 sandbox 내부 loopback에서만 열리므로, sandbox 밖에서 동작하는 **Playwright 브라우저(`:b goto http://localhost:…`)로는 접근할 수 없습니다.** 로컬 서버 대상 브라우저 E2E는 서버를 sandbox 밖에서 띄우거나, 해당 작업에서는 sandbox를 끄세요.

- 네트워크 허용 목록과 파일시스템 규칙 모두 변경 후 `t4g daemon restart`가 필요합니다.
- masking은 설정한 파일과 환경변수만 보호하며 secret scanner가 아닙니다.
- Terminal4GPTWeb은 현재 `@anthropic-ai/sandbox-runtime` **0.0.78** 기준으로 검증했습니다. srt가 아직 0.0.x 계열이므로, 더 최신 버전을 이 프로젝트에서 다시 검증하기 전까지는 이 버전 사용을 권장합니다.

---

## 설정

기본 경로:

```text
~/.config/t4g/config.toml
```

예시:

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
count = 3
names = ["Shell", "Server", "Tests"]
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

환경변수 `NOTION_TOKEN`이 있으면 config의 token보다 우선합니다.

### 다중 터미널

`terminal.count`는 동시에 유지할 PTY 수이며 기본값은 `1`입니다. `terminal.names`는 각 PTY에 대응하는 Notion 자식 페이지 이름입니다.

```toml
[terminal]
count = 3
names = ["Shell", "Server", "Tests"]
```

daemon 하나가 설정된 수만큼 독립 PTY를 띄우고, 선택한 Notion 부모 페이지 바로 아래에 이름별 제어 페이지를 둡니다. `count`는 1~16 범위이며 기본값은 `1`입니다. `names`는 활성 터미널 수만큼 사용되고 페이지 이름은 서로 달라야 합니다.

- 기존 단일 터미널 config는 별도 마이그레이션 작업 없이 `count = 1`로 동작합니다. 이전에 사용자가 지정한 기존 Notion 터미널 페이지 제목도 첫 실행에서 보존합니다.
- `count`를 늘리고 daemon을 재시작하면 부족한 터미널 페이지를 같은 부모 아래에 자동 생성하고 config의 `[[notion.terminals]]` 목록을 갱신합니다.
- 이름을 바꾸고 재시작하면 활성 터미널 페이지 제목도 갱신됩니다.
- `count`를 줄여도 기존 Notion 페이지를 자동 삭제하지 않습니다. 앞에서부터 설정된 수만 활성화되므로 다시 늘릴 때 기존 페이지를 재사용할 수 있습니다.
- 각 PTY는 프로세스, cwd, TUI/REPL 상태, 화면 버퍼, 입력/출력, resize 상태를 독립적으로 유지합니다. 한 터미널의 `:resize`는 다른 터미널 크기에 영향을 주지 않습니다.
- 한 PTY가 종료되어도 다른 PTY는 계속 실행되며, Terminal/Input block 복구도 페이지별로 독립적으로 처리합니다.
- Playwright Browser / Vision surface와 `:b` 명령은 **첫 번째 터미널 페이지에서만** 사용합니다.
- Input polling은 터미널별 round-robin으로 분산하고 health check도 순환시켜 Notion API 요청량이 터미널 수에 비례해 급증하지 않도록 합니다. 터미널 수가 많아질수록 각 페이지의 polling 주기는 자동으로 늘어납니다.

`[[notion.terminals]]`의 page/block ID는 daemon이 생성·복구하면서 관리하는 런타임 값이므로 일반적으로 직접 편집할 필요가 없습니다.

`[sandbox]` 항목 설명은 [PTY sandbox (srt)](#pty-sandbox-srt)를 참고하세요.

config 수정 후:

```bash
t4g daemon restart
```

---

## 진단

```bash
t4g doctor
```

config, Linux / WSL 환경, shell 경로, working directory, Notion page 접근, Terminal/Input block을 확인합니다. `sandbox.enabled = true`이면 sandbox 모드·네트워크 허용 목록·credential 규칙을 표시하고, `srt`·`bwrap`·`socat`·`rg`·`script` 설치를 확인한 뒤 설정된 정책으로 srt에서 `true`를 실행해 봅니다.

---

## 보안

Terminal4GPTWeb은 Claude Code sandbox와 같은 런타임인 [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime) 기반의 **선택적 PTY sandbox**를 지원합니다.

```text
enabled = false
  → daemon 사용자 권한 그대로 실행 (srt 불필요)

enabled = true, read_only = false, workspace = false
  → host 읽기·쓰기 가능, 네트워크는 allowed_domains만

enabled = true, read_only = true, workspace = false
  → host read-only

enabled = true, workspace = true
  → workspace_path 외 사용자 데이터 숨김 (workspace는 RW, read_only = true면 RO)
```

sandbox를 켜면:

- 설정한 경로에만 쓸 수 있고, 셸 rc 파일·git hooks/config·에디터 설정은 srt가 항상 보호합니다.
- 외부 네트워크는 srt 프록시를 통해 `allowed_domains`로만 나갈 수 있습니다.
- 설정한 credential 파일과 환경변수는 `fake_value_<uuid>`로 바뀌고, 실제 값은 해당 credential의 허용 host로만 전달됩니다.

masking은 universal secret scanner가 아니며, 설정한 파일과 환경변수만 보호합니다.

권장사항:

- daemon은 전용 non-root 사용자로 실행
- 개발 작업은 가능하면 `enabled = true` + workspace isolation 사용
- `allowed_domains`는 작업에 필요한 도메인으로만 제한
- 알려진 credential 파일과 환경변수에는 mask 또는 deny 적용
- sudo password/token/private key를 Notion Input에 직접 넣지 않기
- 생성된 Notion control page의 접근 권한 제한
- Docker socket 같은 privileged IPC를 수동으로 노출하면 sandbox 경계를 우회할 수 있다고 간주

---

## 검증 범위

현재 회귀 테스트에는 다음이 포함됩니다.

- Search Page / URL Parent Page wizard
- persistent PTY와 terminal control
- sandbox on/off 실행 경로와 `srt` 미설치 오류
- read-only / workspace / allow-write / deny 규칙, 네트워크 허용 목록, credential 규칙의 srt settings 변환
- Notion runtime block 처리와 browser control helper

GitHub Actions에서는 Python 3.11, 3.12, 3.13으로 전체 테스트를 실행합니다.

sandbox는 실제 `PTYSession → pty.fork() → srt → script → bash` 경로로 환경변수·파일 masking, 외부 HTTP 요청에서의 sentinel→실제 값 치환, 네트워크 허용 목록, deny-write, workspace 격리, Ctrl-C, 터미널 크기 변경까지 E2E 검증했습니다. WSL2 Ubuntu(nvm으로 설치한 srt 0.0.78)에서도 Notion control page를 통해 `tls_terminate` HTTPS 치환(셸에서는 `fake_value_…`, 서버에는 실제 값 도착), 허용되지 않은 도메인의 HTTPS 차단, workspace 격리, 크기 변경을 확인했습니다. Browser는 Notion을 거쳐 Playwright navigation과 Vision payload observation ID까지 smoke test했습니다.

실사용 중인 Notion control page 자체를 삭제하는 것처럼 파괴적인 복구 시나리오는 매 회귀 테스트마다 실제 페이지를 지우는 대신 자동 테스트로 검증합니다.

---

## 한계

Notion은 저지연 터미널 전송 프로토콜이 아닙니다.

터미널 의미론은 유지하지만 모든 입력과 화면 갱신이 Notion API를 거치므로 로컬 터미널보다 지연이 큽니다.

현재 지원하지 않거나 Notion에서 자연스럽게 표현되지 않는 기능:

- 터미널 mouse reporting (Playwright browser mouse control은 지원)
- sixel / kitty graphics
- pixel graphics
- terminal color styling
- clipboard escape sequence
- sub-second keystroke streaming
- WSL / Windows 재시작 후 자동 실행
- srt sandbox 안에서 띄운 서버에 Playwright 브라우저로 접속 ([Sandbox 제약](#sandbox-제약) 참고)

---

## 개발

```bash
pip install -e . pytest
pytest
python -m compileall -q terminal4gptweb tests
```

GitHub Actions에서 Python 3.11, 3.12, 3.13을 테스트합니다.

---

## License

MIT
