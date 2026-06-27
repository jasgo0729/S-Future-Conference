# 2T1F (Two Truths, One Lie)

S-Future-Conference 행사용 **"2개의 진실, 1개의 거짓"** 실시간 게임 모듈입니다.
참가자(팀)가 자신에 대한 진실 2개와 거짓 1개를 작성해 제출하면, 진행자 대시보드에 카드로 실시간 표시됩니다. 관객/진행자는 카드를 열어 각 문장을 클릭하며 진실·거짓을 가려냅니다.

---

## 기술 스택

| 구분 | 내용 |
|------|------|
| 런타임 | Node.js 22 (ESM, `"type": "module"`) |
| 웹 프레임워크 | Express 5 |
| 실시간 통신 | Socket.IO 4 |
| 기타 | cors |
| 프론트엔드 | 순수 HTML/CSS/JS, [SortableJS](https://github.com/SortableJS/Sortable) (드래그 앤 드롭) |
| 컨테이너 | Docker (`node:22-alpine`) |
| 포트 | **3002** |

---

## 디렉터리 구조

```
2T1F/
├── index.js            # Express + Socket.IO 서버 (진입점)
├── package.json
├── Dockerfile
├── .dockerignore
└── public/
    ├── index.html      # 참가자 입력 화면 (진실 2 + 거짓 1 작성/제출)
    └── dashboard.html  # 진행자 대시보드 (제출 카드 표시 + 정답 공개)
```

---

## 동작 방식

서버(`index.js`)는 자체 게임 로직이 없는 **단순 실시간 중계(릴레이) 서버**입니다.

1. 참가자가 `index.html`에서 팀 이름과 문장 3개(진실 2 / 거짓 1)를 작성하고 순서를 드래그로 섞은 뒤 제출합니다.
2. 클라이언트가 `upload` 이벤트로 데이터를 서버에 전송합니다.
3. 서버는 받은 데이터를 그대로 `dashboard` 이벤트로 **연결된 모든 클라이언트에 브로드캐스트**합니다(`io.emit`).
4. `dashboard.html`이 `dashboard` 이벤트를 수신해 새 카드를 화면 맨 앞에 추가합니다.
5. 진행자가 카드를 클릭하면 모달이 열리고, 각 문장을 클릭할 때마다 진실(초록)/거짓(빨강)이 공개됩니다.

```
[참가자 index.html] --upload--> [서버 index.js] --dashboard(broadcast)--> [진행자 dashboard.html]
```

### 주고받는 데이터 형식
```js
{
  group: "1조",                       // 팀/조 이름
  stories: [
    { text: "문장 내용", isTruth: true  },
    { text: "문장 내용", isTruth: false },
    { text: "문장 내용", isTruth: true  }
  ]
}
```
> 진실/거짓 판별 정보(`isTruth`)가 제출 데이터에 그대로 담겨 대시보드로 전달됩니다. 정답은 클라이언트(대시보드)에서만 클릭 시 공개되는 구조입니다.

---

## 라우트 / 이벤트

### HTTP
| 경로 | 설명 |
|------|------|
| `/` | 참가자 입력 화면 (`public/index.html`, 정적 제공) |
| `/dashboard` | 진행자 대시보드 (`public/dashboard.html`) |

### Socket.IO 이벤트
| 이벤트 | 방향 | 설명 |
|--------|------|------|
| `upload` | 클라이언트 → 서버 | 참가자가 작성한 게임 데이터 전송 |
| `dashboard` | 서버 → 전체 | 받은 데이터를 모든 클라이언트에 브로드캐스트 |

---

## 실행 방법

### 로컬 실행
```bash
cd 2T1F
npm install
npm start          # node index.js
```
실행 후:
- 참가자 화면: http://localhost:3002/
- 진행자 대시보드: http://localhost:3002/dashboard

### Docker
```bash
# 이미지 빌드 (프로젝트 루트의 build.sh 사용)
./build.sh 2t1f    # jasgo/sfc_2t1f:latest 로 빌드·푸시

# 또는 직접 빌드
cd 2T1F
docker build -t sfc_2t1f .
docker run -p 3002:3002 sfc_2t1f
```

### docker-compose (전체 통합 실행)
프로젝트 루트의 `docker-compose.yml`에서 `server3` 서비스로 정의되어 있습니다.
```bash
docker compose up -d server3
```

---

## ⚠️ 인계 시 확인 / 주의 사항

- **서버 주소가 하드코딩되어 있습니다.** `public/index.html`과 `public/dashboard.html` 양쪽의 Socket.IO 접속 주소가 특정 EC2 호스트(`ec2-15-165-202-145.ap-northeast-2.compute.amazonaws.com:3002`)로 고정되어 있습니다. 서버 IP/도메인이 바뀌면 **두 HTML 파일을 모두 수정**해야 합니다. (로컬 테스트 시에도 이 주소 때문에 연결되지 않으니 `localhost`로 바꿔야 함)
- **CORS origin 설정이 localhost로 제한**되어 있습니다. `index.js`의 `cors.origin`이 `http://localhost:3002`로 되어 있어, 실제 배포 도메인과 불일치할 경우 연결 문제가 생길 수 있습니다. 운영 환경에 맞게 조정 필요.
- **`build.sh`의 폴더명 대소문자 버그.** 루트 `build.sh`의 `2t1f` 케이스가 소문자 `./2t1f`를 가리키는데 실제 폴더는 `2T1F`입니다. 리눅스(대소문자 구분) 환경에서는 빌드가 실패하므로 수정이 필요합니다.
- **서버에 영속 데이터가 없습니다.** 모든 제출은 메모리를 거치지 않고 즉시 브로드캐스트만 됩니다. 서버 재시작 또는 새로고침 시 기존 카드가 사라지며, 늦게 접속한 대시보드는 그 전 제출 내역을 받지 못합니다.
- **transports가 websocket 전용**으로 지정되어 있어, WebSocket을 막는 네트워크 환경에서는 폴백 없이 연결 실패할 수 있습니다.
