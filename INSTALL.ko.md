# Terminal4GPTWeb 설치 및 최초 설정

[English](./INSTALL.md) · [메인 README](./README.md) · [GPT 시작 프롬프트](./GPT_PROMPT.ko.md) · [제어 명령 전체 레퍼런스](./CONTROL_COMMANDS.ko.md)

이 문서는 Terminal4GPTWeb을 처음 설치하는 사용자를 위한 전체 절차입니다.

완료 후 구조는 다음과 같습니다.

```text
ChatGPT Web
    │
    │ ChatGPT의 Notion 연결
    ▼
Notion
└─ 사용자가 미리 만든 Parent Page
   └─ Terminal4GPTWeb              ← t4g init이 생성
      ├─ Terminal / Input / Browser
      ├─ Terminal4GPTWeb Help
      └─ Browser Vision Payload
              ▲
              │ Notion API
              │
        local t4g daemon
              │
              ├─ Linux PTY
              └─ Playwright Chromium
```

## 1. 준비물

필수:

- Linux 또는 WSL2 Ubuntu
- Python 3.11 이상
- Git
- Bash
- Notion 계정
- Notion API token
- Terminal4GPTWeb이 생성될 위치로 사용할 Notion page
- GPT 웹에서 사용할 경우 ChatGPT의 Notion 연결

선택:

- PTY sandbox를 사용할 경우: Node.js 22.12+, [Anthropic Sandbox Runtime (`srt`)](https://github.com/anthropic-experimental/sandbox-runtime), `bubblewrap`, `socat`, `ripgrep`, `script`(util-linux)
- ChatGPT GitHub 연결 — 코드/이슈/PR 분석과 로컬 테스트를 함께 사용할 경우 권장
- ChatGPT 일정/자동화 — OPS 정기 점검에 활용 가능

버전 확인:

```bash
python3 --version
git --version
bash --version
```

Python이 3.11 미만이면 먼저 3.11 이상의 Python을 설치하세요.

## 2. Linux 패키지 설치

Ubuntu / WSL2 기준:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv
```

PTY sandbox(`sandbox.enabled = true`)를 사용할 예정이라면:

```bash
sudo apt install -y bubblewrap socat ripgrep util-linux
# srt는 Node.js 22.12 이상이 필요합니다
npm install -g @anthropic-ai/sandbox-runtime
srt --version
```

`sandbox.enabled = false`(기본값)로 사용하면 위 도구는 필요하지 않습니다. sandbox를 켰는데 `srt`가 없으면 daemon이 시작을 거부하고 설치 명령을 안내합니다.

## 3. Notion Parent Page 만들기

Notion에서 빈 페이지를 하나 만듭니다.

예:

```text
Terminal4GPTWeb Root
```

현재 Terminal4GPTWeb의 `t4g init`은 생성할 페이지의 **parent page**를 하나 선택합니다.

이 parent page 아래에 자동으로:

```text
Terminal4GPTWeb
├─ Terminal4GPTWeb Help
└─ Browser Vision Payload
```

가 생성됩니다.

Parent Page URL을 반드시 복사해둘 필요는 없습니다. Wizard에서:

```text
1. Search pages
2. Enter URL / page ID
```

중 하나를 사용할 수 있습니다.

## 4. Notion API Token 준비

로컬 `t4g` daemon은 Notion API를 직접 호출합니다. 따라서 **ChatGPT의 Notion 연결과 별도로 Notion API token이 필요합니다.**

두 방식 중 하나를 사용할 수 있습니다.

### 방법 A — Personal Access Token

개인 환경에서는 가장 단순합니다.

1. Notion Developer portal을 엽니다.
2. **Personal access tokens**로 이동합니다.
3. **New token**을 선택합니다.
4. 이름을 지정하고 Notion API capability를 선택합니다.
5. 필요한 경우 workspace를 선택합니다.
6. token을 생성하고 즉시 안전한 곳에 복사합니다.

Notion 공식 문서:
https://developers.notion.com/guides/get-started/quick-start

PAT는 token을 만든 사용자의 Notion page 권한으로 동작합니다.

### 방법 B — Internal Connection

팀용/전용 bot 권한을 분리하고 싶다면 internal connection을 사용할 수 있습니다.

1. Notion Developer portal을 엽니다.
2. **Build → Internal connections**로 이동합니다.
3. **Create a new connection**을 선택합니다.
4. workspace와 이름을 지정합니다.
5. Configuration에서 Installation access token을 복사합니다.
6. Terminal4GPTWeb에 필요한 content capability를 허용합니다.
   - Read content
   - Update content
   - Insert content
7. 만든 Parent Page를 connection에 공유합니다.

페이지 권한 부여 방법은 둘 중 하나입니다.

- Developer portal의 **Content access → Edit access**에서 Parent Page 선택
- Notion Parent Page의 `••• → Connections → Add connection`에서 connection 추가

Parent Page에 권한을 주면 그 아래 생성되는 child page에도 권한이 상속됩니다.

Notion 공식 문서:
https://developers.notion.com/guides/get-started/internal-connections

> Token은 source code, README, Notion Input, Git repository에 넣지 마세요.

## 5. Terminal4GPTWeb 설치

```bash
git clone https://github.com/hyeongmin90/terminal4gptweb.git
cd terminal4gptweb

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -e .
```

설치 확인:

```bash
t4g --version
t4g --help
```

`t4g: command not found`가 나오면 venv가 활성화되어 있는지 확인합니다.

```bash
source ~/terminal4gptweb/.venv/bin/activate
```

프로젝트 폴더를 이동/이름 변경한 뒤 editable install이 깨졌다면:

```bash
cd ~/terminal4gptweb
pip install -e .
hash -r
```

## 6. Playwright Chromium 설치

Browser/Vision 기능을 사용하려면:

```bash
playwright install chromium
```

Linux system dependency가 부족하다는 오류가 나오면:

```bash
playwright install --with-deps chromium
```

Browser 기능을 쓰지 않더라도 Terminal 기능 자체는 사용할 수 있습니다.

## 7. 선택: systemd user service 자동 시작

Terminal4GPTWeb은 systemd를 사용하는 WSL과 일반 Linux를 위해 `contrib/systemd/terminal4gptweb.service`를 제공합니다.

제공되는 unit은 이 문서의 기본 설치 경로를 기준으로 합니다.

```text
~/terminal4gptweb/.venv/bin/t4g
```

설치하고 자동 시작을 활성화하려면:

```bash
mkdir -p ~/.config/systemd/user
cp contrib/systemd/terminal4gptweb.service ~/.config/systemd/user/

# 같은 instance lock을 두 프로세스가 사용하지 않도록 기존 detached daemon 중지
t4g daemon stop

systemctl --user daemon-reload
systemctl --user enable --now terminal4gptweb
systemctl --user status terminal4gptweb
```

저장소나 가상환경 위치가 다르면 사용할 환경에서 `which t4g`로 실제 경로를 확인한 뒤, enable 전에 unit의 `ExecStart`를 해당 경로로 수정합니다.

systemd로 실행할 때 로그는 journal에서 확인합니다.

```bash
journalctl --user -u terminal4gptweb
journalctl --user -u terminal4gptweb -f
```

WSL에서는 WSL/user systemd가 시작될 때 Terminal4GPTWeb이 함께 시작됩니다. 이 설정 자체가 Windows 부팅 시 WSL을 실행시키는 것은 아닙니다. 일반 Linux 서버에서 사용자가 로그인하지 않아도 user service가 부팅 후 실행되어야 한다면 필요에 따라 `loginctl enable-linger "$USER"`를 사용할 수 있습니다.

## 7. 최초 초기화

```bash
t4g init
```

Wizard 순서는 대략 다음과 같습니다.

### Notion API token

```text
Notion API token (PAT or internal connection token):
```

여기에 4단계에서 만든 token을 입력합니다.

입력은 화면에 표시되지 않습니다.

### Parent Page 선택

```text
Choose parent Notion page

  1. Search pages
  2. Enter URL / page ID

Select [1]:
```

#### Search pages

```text
Search page title (blank = recent pages):
```

검색 결과에서 번호를 고릅니다.

```text
1. Terminal4GPTWeb Root
2. Developer Tools

r. Search again
u. Enter URL / page ID
```

#### Enter URL / page ID

Notion에서 Parent Page URL을 복사해 입력할 수도 있습니다.

```text
https://www.notion.so/...
```

URL 전체 또는 page ID 모두 지원합니다.

### Shell

보통 기본값을 그대로 사용합니다.

```text
Shell [/bin/bash]:
```

### Initial working directory

PTY가 시작할 기본 디렉터리입니다.

예:

```text
/home/user/project
```

### PTY sandbox

먼저 sandbox 사용 여부를 묻고, 켠 경우에만 세부 옵션을 묻습니다.

```text
Enable sandbox [y/N]:
Read-only filesystem [y/N]:
Restrict filesystem to one workspace [y/N]:
Workspace path [...] :        # workspace=true일 때만
Extra writable paths (comma-separated, optional, e.g. ~/.cache):
Deny read paths (comma-separated, optional):
Deny write paths (comma-separated, optional):
Allowed network domains (comma-separated, '-' = no network) [github.com,...]:
```

sandbox를 켰는데 srt나 시스템 도구가 없으면 wizard가 경고하지만 설정은 저장됩니다.

조합:

- `enabled=false`: 일반 PTY (srt 불필요)
- `read_only=false, workspace=false`: host 전체 읽기·쓰기 가능
- `read_only=true, workspace=false`: host 전체 read-only
- `read_only=false, workspace=true`: 지정 workspace만 보이고 RW
- `read_only=true, workspace=true`: 지정 workspace만 보이고 workspace 자체도 read-only

Credential masking 규칙은 초기화 후 config에서 명시적으로 설정합니다.

### 나머지 설정

```text
Prompt user
Prompt host
Terminal columns
Terminal rows
Input poll interval
Screen refresh interval
Notion page title
```

대부분 기본값으로 시작해도 됩니다.

## 8. 생성되는 파일과 Notion 페이지

로컬 설정:

```text
~/.config/t4g/config.toml
```

runtime:

```text
~/.cache/notion_is_terminal/
├─ daemon.pid
├─ daemon.log
├─ instance.lock
└─ ...
```

Notion:

```text
Parent Page
└─ Terminal4GPTWeb
   ├─ Terminal
   ├─ Input
   ├─ Quick Commands
   ├─ Browser Status
   ├─ Browser Screenshot
   ├─ Terminal4GPTWeb Help
   └─ Browser Vision Payload
```

## 9. Sandbox 설정 (srt)

`enabled`가 전체 스위치입니다. 켜면 셸이 [Anthropic Sandbox Runtime (srt)](https://github.com/anthropic-experimental/sandbox-runtime) 안에서 실행되고, t4g가 `[sandbox]` 설정으로 `~/.cache/notion_is_terminal/srt-settings.json`을 만들어 srt에 넘깁니다.

예:

```toml
[sandbox]
enabled = true
srt_path = ""             # 비워두면 PATH의 srt 사용
read_only = false
workspace = true
workspace_path = "/home/user/project"
allow_read = ["~/.nvm"]       # workspace 모드에서도 보여야 하는 $HOME 아래 도구
allow_write = ["~/.cache"]
deny_read = []
deny_write = [".git"]
allowed_domains = ["github.com", "*.githubusercontent.com", "pypi.org", "files.pythonhosted.org"]
denied_domains = []
tls_terminate = true
allow_plaintext_inject = false
```

### Sandbox OFF

```toml
[sandbox]
enabled = false
```

srt를 거치지 않고 기존 PTY처럼 실행됩니다. 나머지 항목은 남겨둬도 무시됩니다.

### Host 모드 (쓰기 가능)

```toml
[sandbox]
enabled = true
read_only = false
workspace = false
```

효과:

- host filesystem 읽기·쓰기 가능
- srt 보호 파일(`.bashrc`, `.gitconfig`, `.git/hooks` 등)은 쓰기 차단
- 네트워크는 `allowed_domains`만 허용

### Read-only

```toml
[sandbox]
enabled = true
read_only = true
workspace = false
allow_write = []
```

효과:

- host filesystem read 가능
- host filesystem write 차단 (`allow_write` 경로만 예외)
- 임시 파일은 srt가 지정한 `TMPDIR`(`/tmp/claude`)에 쓸 수 있음

### Workspace 격리

```toml
[sandbox]
enabled = true
read_only = false
workspace = true
workspace_path = "/home/user/project"
```

효과:

- `/home`, `/root`, `/mnt`, `/media`는 숨기고 workspace만 보임
- workspace는 RW, 셸은 workspace에서 시작
- 경로는 실제 경로 그대로 보임 (`/workspace`로 바뀌지 않음)
- 시스템 경로(`/usr`, `/etc` 등)는 읽기만 가능
- 캐시처럼 추가로 쓸 경로는 `allow_write`에 지정 (예: `~/.cache`, `~/.npm`)
- nvm으로 설치한 node처럼 홈 아래 도구를 쓰려면 `allow_read`에 지정 (예: `~/.nvm`). srt 자체 패키지는 자동으로 읽기 허용

### Workspace + Read-only

```toml
[sandbox]
enabled = true
read_only = true
workspace = true
workspace_path = "/home/user/project"
```

workspace만 보이며 workspace 자체도 read-only입니다.

### 쓰기 제어 범위

- `allow_write`: 추가로 쓰기 허용할 경로
- `deny_write`: 쓰기 가능한 영역 안에서 다시 막을 경로 (`allow_write`보다 우선)
- Linux에서는 실제 경로 단위로만 지정할 수 있습니다(glob 불가). 생성·수정·삭제는 구분되지 않습니다.
- 파일시스템 규칙은 셸 시작 시 고정되므로 변경 후 `t4g daemon restart`가 필요합니다.

### 네트워크

- `allowed_domains`에 있는 도메인만 접근 가능합니다(`*.example.com` 가능, `*` 단독은 srt가 거부).
- `denied_domains`가 우선합니다.
- 목록이 비어 있으면 네트워크가 완전히 차단됩니다.
- sandbox 터미널 안에서 띄운 서버는 별도 네트워크 namespace에 있으므로 **Playwright 브라우저에서 접근할 수 없습니다.** 로컬 서버 E2E는 서버를 sandbox 밖에서 띄우세요.

### Credential masking

```toml
[[sandbox.credentials.files]]
path = ".env"
mode = "mask"
extract = '(?m)^(?:OPENAI_API_KEY|DATABASE_URL|JWT_SECRET)=(\S+)$'
on_extract_no_match = "deny"
mask_duplicates = false
inject_hosts = ["api.openai.com"]

[[sandbox.credentials.env]]
name = "GITHUB_TOKEN"
mode = "mask"
inject_hosts = ["api.github.com"]
```

실제:

```dotenv
OPENAI_API_KEY=sk-real
DATABASE_URL=postgres://real
PORT=8080
```

sandbox 내부:

```dotenv
OPENAI_API_KEY=fake_value_<uuid>
DATABASE_URL=fake_value_<uuid>
PORT=8080
```

환경변수도 마찬가지로 `echo $GITHUB_TOKEN`은 `fake_value_<uuid>`를 출력합니다. 프로그램이 이 값을 담아 `inject_hosts`로 HTTP(S) 요청을 보내면, srt 프록시가 요청이 나가는 시점에 실제 값으로 바꿉니다. `inject_hosts`를 생략하면 srt는 모든 `allowed_domains`를 기본 범위로 사용합니다.

- `extract`의 **capture group 1**만 masking됩니다(정확히 하나의 group 필요). 생략하면 파일/값 전체가 바뀝니다.
- `mode = "deny"`: 파일은 읽을 수 없고, 환경변수는 제거됩니다. credential을 sandbox에서 사용하거나 외부로 주입할 수 없게 하려면 이 모드를 사용합니다.
- 현재 srt는 `mode = "mask"`에서 `inject_hosts = []`를 거부합니다. Terminal4GPTWeb도 이를 설정 오류로 처리해 빈 배열이 의도치 않게 전체 허용으로 넓어지는 것을 막습니다.
- `on_extract_no_match`: `warn`(그대로 노출, fail-open), `deny`(숨김, fail-closed), `error`(시작 거부)
- HTTPS 요청에서 치환하려면 `tls_terminate = true`가 필요합니다. `allow_plaintext_inject = true`는 이를 명시적으로 끄는 옵션이며 평문 HTTP에만 치환합니다.
- SSH, DB 프로토콜 등 HTTP가 아닌 연결에는 가짜 값이 그대로 전달됩니다.

보수적인 credential 설정에는 `deny` 또는 `error`를 권장합니다.

설정을 수정했다면:

```bash
t4g daemon restart
```

## 10. 진단

```bash
t4g doctor
```

확인 항목:

- config parsing
- Linux / WSL
- shell
- working directory
- sandbox 켜짐 여부, 모드, 네트워크 허용 목록, credential 규칙 개수
- sandbox를 켠 경우 `srt`, `bwrap`, `socat`, `rg`, `script` 설치 여부
- workspace 존재 여부
- 설정된 정책으로 srt에서 `true` 실행 (smoke test)
- Notion page
- Terminal/Input blocks
- Playwright Python package

문제가 있다면:

```bash
t4g daemon logs
t4g daemon logs -f
```

도 확인합니다.

## 11. Daemon 실행

```bash
t4g daemon start
t4g daemon status
```

Foreground 디버깅:

```bash
t4g run
```

정지/재시작:

```bash
t4g daemon stop
t4g daemon restart
```

## 12. ChatGPT Web에서 Notion 연결

이 단계는 **로컬 Notion API token 설정과 별개**입니다.

ChatGPT에서 계정에 표시되는 Apps 또는 Plugins 설정을 열고 Notion을 연결합니다.

현재 OpenAI 도움말 기준 일반 흐름:

1. ChatGPT의 Apps/Plugins 설정을 엽니다.
2. Notion을 찾습니다.
3. Connect 또는 Install/Connect를 선택합니다.
4. 사용할 Notion 계정에 로그인합니다.
5. Terminal4GPTWeb 페이지가 있는 workspace/content에 대한 연결을 승인합니다.

OpenAI 도움말:
https://help.openai.com/en/articles/12532955-notion-app-and-setup-in-chatgpt

ChatGPT가 Terminal4GPTWeb 페이지를 찾지 못하면:

- 다른 Notion 계정을 연결하지 않았는지
- 다른 workspace를 연결하지 않았는지
- 해당 계정이 Parent/Terminal4GPTWeb 페이지를 볼 수 있는지
- 연결 승인 범위에 페이지가 포함되는지

확인합니다.

## 13. 첫 테스트

먼저 Notion의 Terminal4GPTWeb 페이지를 직접 열고 Input에:

```text
pwd
```

처럼 입력하고 Enter를 한 번 누르면 제출됩니다.

정상이라면 Terminal이 갱신되고 Input은 다시 빈 블록으로 초기화됩니다.


로 초기화됩니다.

다음:

```text
whoami
```

를 테스트합니다.

Browser:

```text
:b goto https://example.com
```

Browser Status와 Browser Screenshot이 갱신되면 브라우저도 정상입니다.

## 14. ChatGPT에서 첫 요청

새 ChatGPT Web 대화를 시작할 때는 준비해 둔 **[GPT 시작 프롬프트](./GPT_PROMPT.ko.md)**를 첫 메시지로 그대로 붙여 넣는 것을 권장합니다. GPT가 먼저 `Terminal4GPTWeb Help`를 읽고 Input/Browser 제어 규칙을 익힌 뒤 현재 Terminal까지 확인하게 됩니다.

그 다음부터는 평소처럼 작업을 요청하면 됩니다.

```text
현재 Terminal에서 pwd를 실행하고 결과를 알려줘.
```

개발에 GitHub도 연결했다면:

```text
GitHub에서 이 저장소의 최근 변경사항을 확인하고,
Terminal4GPTWeb으로 로컬 테스트를 실행해줘.
필요하면 Playwright로 웹 화면도 검증해줘.
```

## 15. 페이지가 삭제된 경우

Terminal/Input block만 삭제된 경우 daemon이 자동 복구를 시도합니다.

메인 Terminal4GPTWeb page 전체를 삭제했다면:

```bash
t4g reinit
t4g daemon restart
```

저장된 `parent_page_id`가 있으면 같은 parent 아래에 새 control page를 만듭니다.

오래된 config라 parent 정보가 없으면 Search Page / URL 선택 UI가 다시 표시됩니다.

## 16. 보안 체크리스트

- daemon은 root로 실행하지 않기
- Notion Input에 password/token/private key 직접 입력하지 않기
- 가능하면 `sandbox.enabled = true` + workspace 격리 사용
- `allowed_domains`는 작업에 필요한 도메인으로만 제한
- credential 파일과 환경변수는 masking 또는 deny 정책 적용
- `.git`, 중요한 설정 디렉터리는 필요하면 `deny_write`
- Notion control page 접근 권한 제한
- masking은 **설정된 파일/환경변수만** 보호하며 universal secret scanner가 아님
- 실제 값 치환은 srt 프록시를 거치는 HTTP(S) 요청에만 적용됨
- Docker socket을 sandbox에 노출하는 기능은 현재 제공하지 않음

## 다음 문서

- [README.ko.md](./README.md) — 전체 기능 및 사용법
- [INSTALL.md](./INSTALL.md) — English installation guide
