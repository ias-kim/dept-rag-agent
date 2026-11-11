# 배포 — EC2 1대에 앱·DB·Caddy

> 마지막 갱신: 2026-11-06 · 계획: [`m4b-deploy`](../exec-plans/active/2026-11-06-m4b-deploy.md)

## 1. 핵심 개념

- **입구는 Caddy 하나.** 인터넷에서 닿는 것은 80·443뿐이다. 앱과 DB에 포트를 열면 HTTPS와 로그인 제한을 건너뛰는 길이 생긴다.
- **스택 하나가 자원 전부.** 전용 VPC에 모아 두고 `dept-rag-prod` 스택 삭제로 내 자원만 정리한다.
- **비밀값은 서버 `.env`에만.** 레포가 PUBLIC이고 스택 파라미터는 콘솔에 보인다. `JWT_SECRET`·`DB_PASSWORD`는 서버에서 처음 한 번 생성하고, API 키는 사람이 넣는다.
- **이미지는 서버에서 빌드.** t3.small(2GiB)에서는 프론트 빌드가 메모리를 넘길 수 있어 스왑 2GiB를 둔다.

## 2. 데이터 흐름

```
브라우저 → 443 Caddy(172.30.0.10) → app:8000 → db:5432
             └ 80은 443으로 돌려보내고, 인증서 발급 확인에만 쓴다

배포:  git archive HEAD → ssh tar → docker compose up --build --wait
색인:  로컬 pg_dump(documents·chunks) → ssh 파이프 → 서버 psql
```

### 처음부터 다시 올리기

리전은 명령마다 명시한다. 먼저 `aws sts get-caller-identity`로 계정을 확인한다.

```bash
aws cloudformation create-stack --region <리전> --stack-name dept-rag-prod \
  --template-body file://infra/stack.yaml --capabilities CAPABILITY_IAM \
  --parameters ParameterKey=DeployRegion,ParameterValue=<리전> ParameterKey=AdminCidr,ParameterValue=<내 IP>/32 \
    ParameterKey=KeyName,ParameterValue=<키 페어> ParameterKey=ImageId,ParameterValue=<Ubuntu 24.04 amd64 AMI>
SSH_KEY=<키 파일> infra/deploy.sh <IP> <대시로 쓴 IP>.sslip.io
infra/restore-index.sh <IP>
```

그다음 서버 `~/dept-rag/.env`의 `ANTHROPIC_API_KEY`·`OPENAI_API_KEY`를 사람이 채우고 `infra/deploy.sh`를 다시 실행한다. 계정 생성은 `docker compose ... exec -T app python -m app.core.users add <이름> --courses AGENT,DB --password-stdin`.

## 3. 불변 조건과 실패 모드

| 조건 | 깨지면 생기는 문제 | 지키는 장치 |
|---|---|---|
| `FORWARDED_ALLOW_IPS` = Caddy 고정 주소 | 모든 사용자가 한 IP로 보여 로그인 제한이 한꺼번에 막히거나, 위조 헤더로 제한을 피한다 | `test_app_trusts_only_caddy_for_forwarded_headers` |
| DB·앱은 포트를 공개하지 않는다 | HTTPS·로그인 제한 우회, DB 직접 공격 | `test_only_caddy_publishes_ports`, 보안 그룹 |
| SSH는 관리자 IP만 | 전 세계에서 비밀번호·취약점 공격 | `test_security_group_exposes_only_web_to_the_world` |
| 메타데이터 홉 제한 1 | 앱이 뚫리면 컨테이너에서 인스턴스 역할 자격 증명을 가져간다 | `test_instance_blocks_container_access_to_role_credentials` |
| 리전은 배포 때 명시 | CLI 기본값 때문에 엉뚱한 리전에 자원이 생긴다 | `test_stack_refuses_a_region_other_than_the_one_stated_at_deploy` |
| AMI는 파라미터로 고정 | 스택 갱신 때 인스턴스가 교체되어 DB 볼륨이 사라진다 | `test_instance_ami_is_pinned_by_parameter` |
| 서버 `.env`는 덮어쓰지 않는다 | `DB_PASSWORD`가 바뀌어 DB 접속 실패, `JWT_SECRET`이 바뀌어 전원 로그아웃 | `infra/deploy.sh`의 파일 존재 검사 |
| 로컬 `users`를 옮기지 않는다 | 시험 계정이 공개 서버에서 살아난다 | `infra/restore-index.sh`의 `-t documents -t chunks` |

외부 요인으로 실패할 때:

- **API 키가 비었거나 틀림**: `/health`와 로그인은 되지만 질문에 답하지 못한다.
- **관리자 IP가 바뀜**: SSH 시간 초과. 스택의 `AdminCidr`를 갱신하거나 SSM으로 들어간다.
- **`caddy-data` 볼륨 삭제**: 인증서를 다시 받는다. 반복하면 발급 한도에 걸린다.
- **인스턴스 재시작**: 컨테이너는 `restart: unless-stopped`로 올라오고 EIP도 유지된다.

## 4. 다음 수정

- `pg_dump`의 S3 백업 자동화 — 지금은 DB 볼륨이 인스턴스에 하나뿐이라 인스턴스를 잃으면 계정이 함께 사라진다.
- PDF의 S3 동기화(M6). 공용 계정의 접근 범위를 교수님께 확인한 뒤 진행한다(설계 §9).
- 도메인을 DuckDNS로 옮기려면 서버 `.env`의 `DOMAIN`만 바꾸고 `infra/deploy.sh`를 다시 실행한다.

## 5. 업데이트 시 주의점

- `AWS::EC2::Instance`의 `UserData`·`ImageId`·`InstanceType` 변경은 재시작이나 교체를 부른다. 스택 갱신 전에 change set으로 확인한다.
- 스택 삭제 전에 버킷을 비운다. 비어 있지 않으면 삭제가 실패한다(데이터를 조용히 지우지 않으려는 의도).
- `docker/`와 `infra/`는 위험 경로다. 게이트 3 대상.
