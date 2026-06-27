# Buzzer (선착순 버저)

S-Future-Conference 행사용 **실시간 선착순 버저** 모듈입니다.
퀴즈 등에서 참가자가 버튼을 누른 순서를 진행자 대시보드에 실시간으로 표시합니다. 참가자가 버튼을 누르면 효과음과 함께 누른 사람의 번호가 대시보드 램프에 순서대로 점등됩니다.

---

## 기술 스택

| 구분 | 내용 |
|------|------|
| 런타임 | Node.js 22 (ESM, `"type": "module"`) |
| 웹 프레임워크 | Express 5 |
| 실시간 통신 | Socket.IO 4 |
| 프론트엔드 | 순수 HTML/CSS/JS, 효과음(`buzzer.mp3`) |
| 컨테이너 | Docker (`node:22-alpine`) |
| 포트 | **3001** |

---

## 디렉터리 구조

```
Buzzer/
├── index.js              # Express + Socket.IO 서버 (진입점)
├── package.json
├── Dockerfile
├── .dockerignore
└── public/
    ├── index.html        # 입장 화면 (번호 1~8 입력 → localStorage 저장)
    ├── buzzer.html       # 참가자 버저 화면 (PRESS 버튼)
    ├── dashboard.html    # 진행자 대시보드 (누른 순서 램프 표시)
    └── buzzer.mp3        # 버저 효과음
```

---

## 동작 방식

서버(`index.js`)는 누가 어떤 socket으로 접속했는지 매핑만 관리하는 **실시간 중계 서버**입니다.

1. 참가자가 `index.html`에서 자기 번호(1~8)를 입력하면 `localStorage`에 저장되고 `/buzzer` 화면으로 이동합니다.
2. `buzzer.html` 접속 시 `user_join` 이벤트로 자기 번호를 서버에 등록합니다. 서버는 `socket.id ↔ 번호`를 `Map`에 저장합니다.
3. 참가자가 PRESS 버튼을 누르면 효과음이 재생되고 `buzzer` 이벤트가 서버로 전송됩니다.
4. 서버는 누른 사람의 번호를 `dashboard` 이벤트로 **전체 브로드캐스트**합니다.
5. `dashboard.html`이 이를 받아 해당 번호 램프를 누른 순서대로 점등합니다.

```
[입장 index.html] --번호 저장--> [buzzer.html] --user_join/buzzer--> [서버] --dashboard(broadcast)--> [dashboard.html]
```

---

## 라우트 / 이벤트

### HTTP
| 경로 | 설명 |
|------|------|
| `/` | 입장 화면 (`public/index.html`, 정적 제공) |
| `/buzzer` | 참가자 버저 화면 (`public/buzzer.html`) |
| `/dashboard` | 진행자 대시보드 (`public/dashboard.html`) |

### Socket.IO 이벤트
| 이벤트 | 방향 | 설명 |
|--------|------|------|
| `user_join` | 클라이언트 → 서버 | 참가자 번호 등록 (`socket.id ↔ 번호` 매핑) |
| `buzzer` | 클라이언트 → 서버 | 버저 클릭 |
| `dashboard` | 서버 → 전체 | 누른 사람의 번호를 모든 클라이언트에 브로드캐스트 |

---

## 실행 방법

### 로컬 실행
```bash
cd Buzzer
npm install
npm start          # node index.js
```
실행 후:
- 입장 화면: http://localhost:3001/
- 진행자 대시보드: http://localhost:3001/dashboard

### Docker / compose
```bash
./build.sh buzzer              # jasgo/sfc_buzzer:latest 빌드·푸시
docker compose up -d server2   # compose의 server2 서비스
```

---

## ⚠️ 인계 시 확인 / 주의 사항

- **하드코딩된 서버 주소.** `buzzer.html`과 `dashboard.html` 양쪽의 Socket.IO 접속 주소가 특정 EC2 호스트(`ec2-15-165-202-145.ap-northeast-2.compute.amazonaws.com:3001`)로 고정되어 있습니다. 서버 IP/도메인이 바뀌면 두 파일을 모두 수정해야 하며, 로컬 테스트 시에도 `localhost`로 바꿔야 연결됩니다.
- **번호 범위가 1~8로 제한**되어 있습니다(`index.html`의 입력 `min=1 max=8`). 팀/참가자 수가 다르면 조정 필요. 번호는 사용자가 직접 입력하므로 중복 입력을 막는 검증은 없습니다.
- **CORS origin이 localhost로 제한**되어 있어(`index.js`) 실제 배포 도메인과 불일치 시 연결 문제가 생길 수 있습니다.
- **무상태 구조.** 누른 순서를 서버에 저장하지 않고 즉시 브로드캐스트만 합니다(코드의 `buzzerClickOrder` 배열은 주석 처리됨). 대시보드 새로고침 시 점등 상태가 초기화됩니다.
- **transports가 websocket 전용**이라 WebSocket을 막는 네트워크에서는 폴백 없이 연결 실패할 수 있습니다.
- **효과음 재생 제약.** 모바일 브라우저는 사용자 상호작용 전 자동 오디오 재생을 막으므로, 첫 클릭 전까지 `buzzer.mp3`가 안 울릴 수 있습니다.
