"""운영 설정의 불변 조건 — 어기면 배포 뒤에야 사고로 드러나는 것들. 설명: docs/dev-notes/deploy.md"""

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
COMPOSE = REPO / "docker" / "docker-compose.prod.yml"
STACK = REPO / "infra" / "stack.yaml"
CADDYFILE = REPO / "docker" / "Caddyfile"


class _CfnLoader(yaml.SafeLoader):
    """!Ref·!Sub 같은 CloudFormation 단축 태그를 값 그대로 읽는다."""


_CfnLoader.add_multi_constructor(
    "!",
    lambda loader, suffix, node: {
        suffix: (
            loader.construct_scalar(node)
            if isinstance(node, yaml.ScalarNode)
            else loader.construct_sequence(node, deep=True)
            if isinstance(node, yaml.SequenceNode)
            else loader.construct_mapping(node, deep=True)
        )
    },
)


@pytest.fixture(scope="module")
def services():
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


@pytest.fixture(scope="module")
def resources():
    return yaml.load(STACK.read_text(encoding="utf-8"), Loader=_CfnLoader)["Resources"]


def _of_type(resources, type_name):
    return [r for r in resources.values() if r["Type"] == type_name]


def test_only_caddy_publishes_ports(services):
    # 앱이나 DB가 포트를 열면 HTTPS와 로그인 제한을 건너뛰는 입구가 생긴다
    assert "ports" not in services["db"]
    assert "ports" not in services["app"]
    assert set(services["caddy"]["ports"]) == {"80:80", "443:443"}


def test_app_trusts_only_caddy_for_forwarded_headers(services):
    # 어긋나면 모든 사용자가 같은 IP로 보여 로그인 제한이 한꺼번에 막거나, 위조한 헤더로 제한을 피한다
    caddy_ip = services["caddy"]["networks"]["web"]["ipv4_address"]
    assert services["app"]["environment"]["FORWARDED_ALLOW_IPS"] == caddy_ip


def test_no_secret_is_hardcoded_in_compose(services):
    # 레포가 PUBLIC이므로 여기 적은 값은 곧 공개된 값이다
    assert services["db"]["environment"]["POSTGRES_PASSWORD"] == "${DB_PASSWORD:?}"
    assert "${DB_PASSWORD:?}" in services["app"]["environment"]["DATABASE_URL"]


def test_caddy_serves_the_configured_domain_and_proxies_app():
    text = CADDYFILE.read_text(encoding="utf-8")
    assert "{$DOMAIN}" in text
    assert "reverse_proxy app:8000" in text


def test_security_group_exposes_only_web_to_the_world(resources):
    groups = _of_type(resources, "AWS::EC2::SecurityGroup")
    assert len(groups) == 1
    rules = groups[0]["Properties"]["SecurityGroupIngress"]
    public_ports = {r["FromPort"] for r in rules if r.get("CidrIp") == "0.0.0.0/0"}
    assert public_ports == {80, 443}
    ssh = [r for r in rules if r["FromPort"] == 22]
    assert ssh == [{"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "CidrIp": {"Ref": "AdminCidr"}}]


def test_instance_blocks_container_access_to_role_credentials(resources):
    # 홉 제한 1이면 컨테이너가 메타데이터에 닿지 못한다 — 앱이 뚫려도 인스턴스 역할을 훔치지 못한다
    instance = _of_type(resources, "AWS::EC2::Instance")[0]["Properties"]
    assert instance["MetadataOptions"] == {"HttpTokens": "required", "HttpPutResponseHopLimit": 1}


def test_instance_ami_is_pinned_by_parameter(resources):
    # SSM 최신 AMI를 쓰면 스택 갱신 때 인스턴스가 교체되어 DB 볼륨이 사라진다
    instance = _of_type(resources, "AWS::EC2::Instance")[0]["Properties"]
    assert instance["ImageId"] == {"Ref": "ImageId"}


def test_bucket_blocks_public_access(resources):
    # 전공 자료 원문이 담긴 백업이 올라가는 버킷이다
    bucket = _of_type(resources, "AWS::S3::Bucket")[0]["Properties"]
    block = bucket["PublicAccessBlockConfiguration"]
    assert all(block[k] is True for k in
               ("BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"))
