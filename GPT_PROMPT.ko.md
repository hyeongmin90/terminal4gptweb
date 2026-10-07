# Terminal4GPTWeb GPT 시작 프롬프트

[English](./GPT_PROMPT.md) · [메인 README](./README.md) · [제어 명령 전체 레퍼런스](./CONTROL_COMMANDS.ko.md)

아래 프롬프트를 새 ChatGPT Web 대화에 그대로 붙여 넣으면 됩니다.

```text
이 대화에서는 Terminal4GPTWeb을 내 로컬 터미널 및 브라우저 제어 도구로 사용해.

Notion 연결에서 "Terminal4GPTWeb" 제어 페이지를 찾고, 작업을 시작하기 전에 그 아래의 "Terminal4GPTWeb Help" child page를 먼저 읽어. Help 페이지에 적힌 내용을 이 대화의 Terminal4GPTWeb 사용 규칙으로 따라.

기본 동작 규칙:
- Terminal 또는 Browser Status를 먼저 관찰한 뒤 행동해.
- Notion의 Input에는 한 번에 하나의 action만 작성해.
- **Input은 실제 text가 newline으로 끝나야 실행돼.** 명령 문자열만 써 놓고 마지막 줄바꿈이 없으면 실행되지 않아. Notion connector/API로 수정할 때 trailing newline이 남도록 하고, Markdown 코드블록 방식이면 명령 뒤 빈 줄 하나를 둔 뒤 코드블록을 닫아. 명령이 Input에 그대로 남아 있으면 이 newline 누락부터 확인해.
- 한 번의 제출은 최대 4000 bytes(UTF-8, 한글은 글자당 3 bytes)야. 넘으면 전송되지 않고 Terminal에 `[Terminal4GPTWeb] Input not sent: ...`가 표시돼. 파일처럼 긴 내용은 `cat >> file <<'EOF'`로 여러 번 나눠 제출해.
- Input을 작성한 뒤 Input이 다시 초기화되고 결과가 갱신될 때까지 기다린 다음 다음 action을 수행해.
- 일반 문자열과 제어 명령을 한 번에 섞지 마. 예를 들어 Codex/Claude Code 같은 TUI에 문자열을 입력한 뒤 실제 Enter가 필요하면 문자열을 먼저 제출하고, 다음 Input action으로 ":k ENTER"만 별도로 제출해.
- ":k", ":c", ":s", ":rs", ":b" 같은 Terminal4GPTWeb 제어 명령은 해당 프로그램의 채팅/입력창에 타이핑하는 문자열이 아니라 Notion Input에서 해석되는 별도 control action이야.
- Browser를 조작할 때는 최신 Browser Status와 같은 observation_id의 Screenshot 또는 Vision Payload를 기준으로 판단해.
- move/click/drag에는 반드시 최신 observation_id를 사용하고, browser action 하나를 수행할 때마다 새 ready observation을 기다린 뒤 다음 action으로 넘어가.
- Browser Status가 failed이면 error를 먼저 확인하고, 이전 screenshot 좌표를 계속 사용하지 마.
- Input에 [SANDBOX UNAVAILABLE]이 보이면 명령을 반복하지 말고 필요한 sandbox/SRT 상태를 알려줘.
- 비밀번호, API key, SSH private key 같은 비밀정보를 Notion Input에 직접 쓰지 마.
- 터미널 출력이나 브라우저 결과를 내가 직접 복사해서 전달하도록 요구하지 말고, 연결된 Notion 페이지에서 직접 다시 읽어.
- 필요한 경우 Terminal4GPTWeb Help와 제어 명령 문서를 다시 확인해 추측하지 말고 실제 지원되는 명령만 사용해.

내가 로컬 프로젝트 확인, 수정, 실행, 테스트, 디버깅을 요청하면 가능한 범위에서 다음 흐름으로 계속 진행해:
observe → action 하나 실행 → 결과 재관찰 → 다음 action.

GitHub 연결도 사용할 수 있다면 저장소의 코드/이슈/PR/변경 이력 확인에는 GitHub를 사용하고, 로컬 실행·빌드·테스트·TUI 조작은 Terminal4GPTWeb을 사용해.

이제 먼저 Notion에서 Terminal4GPTWeb 페이지와 Terminal4GPTWeb Help 페이지를 찾고 Help를 읽은 뒤, 현재 Terminal 상태를 확인해. 아직 실제 작업 요청이 없다면 그 상태까지만 확인하고 대기해.
```

## 사용 방법

1. Terminal4GPTWeb을 설치하고 `t4g daemon start`로 daemon을 실행합니다.
2. ChatGPT Web에 Notion 연결을 추가하고 Terminal4GPTWeb 페이지가 있는 workspace에 접근 권한을 줍니다.
3. 위 프롬프트를 새 대화의 첫 메시지로 붙여 넣습니다.
4. GPT가 Notion에서 `Terminal4GPTWeb Help`를 읽고 현재 Terminal 상태까지 확인하면 준비가 끝납니다.
5. 이후 같은 대화에서 평소처럼 작업을 요청합니다.

예:

```text
현재 프로젝트에서 테스트 실패 원인을 확인하고 수정해줘.
```

또는:

```text
서버 실행하고 브라우저로 로그인 화면까지 확인해줘.
```

이 프롬프트는 모든 command 문법을 중복해서 포함하지 않습니다. 실제 명령과 세부 동작은 생성된 Notion `Terminal4GPTWeb Help`와 [CONTROL_COMMANDS.ko.md](./CONTROL_COMMANDS.ko.md)를 기준으로 합니다.
