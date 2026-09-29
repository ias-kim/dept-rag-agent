"""평가셋 로드·검증·동결 — 설계 §6. SoT는 eval/questions.yaml."""

import argparse
import hashlib
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

INTENTS = frozenset({"major", "academic", "both", "none"})
REPO_ROOT = Path(__file__).resolve().parents[2]
QUESTIONS = REPO_ROOT / "eval" / "questions.yaml"
FROZEN = REPO_ROOT / "eval" / "FROZEN"


@dataclass(frozen=True)
class GoldSource:
    file: str
    page: int


@dataclass(frozen=True)
class EvalItem:
    id: str
    question: str
    intent: str
    gold_sources: tuple[GoldSource, ...]
    key_points: tuple[str, ...]


def _item(raw: dict, index: int) -> EvalItem:
    if not isinstance(raw, dict):
        raise ValueError(f"#{index}: 항목이 매핑이어야 함")

    # id 검증 (필수, 비어있지 않은 문자열)
    item_id = raw.get("id")
    if item_id is None:
        raise ValueError(f"#{index}: id가 필요함")
    if not isinstance(item_id, str) or not item_id:
        raise ValueError(f"#{index}: id는 비어있지 않은 문자열이어야 함")

    label = item_id
    question = str(raw.get("question") or "").strip()
    intent = raw.get("intent")
    if not question:
        raise ValueError(f"{label}: question이 비어 있음")
    if intent not in INTENTS:
        raise ValueError(f"{label}: intent는 {sorted(INTENTS)} 중 하나")

    # gold_sources 검증: missing/null은 [] 취급, 있으면 list여야 함
    gold_sources_raw = raw.get("gold_sources")
    if gold_sources_raw is None:
        gold_sources_raw = []
    elif not isinstance(gold_sources_raw, list):
        raise ValueError(f"{label}: gold_sources는 목록이어야 함")

    gold = []
    for g in gold_sources_raw:
        if not isinstance(g, dict):
            raise ValueError(f"{label}: gold_sources의 각 항목은 매핑이어야 함")

        file_val = g.get("file")
        if file_val is None or not isinstance(file_val, str) or not file_val:
            raise ValueError(f"{label}: gold_sources의 file이 필요함")

        page = g.get("page")
        if not isinstance(page, int) or isinstance(page, bool) or page < 1:
            raise ValueError(f"{label}: gold_sources의 page는 1 이상의 정수")

        # Normalize file to NFC
        normalized_file = unicodedata.normalize("NFC", file_val)
        gold.append(GoldSource(normalized_file, page))

    # key_points 검증: missing/null은 [] 취급, 있으면 list여야 함
    key_points_raw = raw.get("key_points")
    if key_points_raw is None:
        key_points_raw = []
    elif not isinstance(key_points_raw, list):
        raise ValueError(f"{label}: key_points는 목록이어야 함")

    # key_points의 각 원소가 문자열인지 검증 (str() 강제 변환 금지)
    key_points = []
    for k in key_points_raw:
        if not isinstance(k, str):
            raise ValueError(f"{label}: key_points는 문자열 목록이어야 함")
        key_points.append(k)
    key_points = tuple(key_points)

    if intent == "none" and gold:
        raise ValueError(f"{label}: intent none에는 gold_sources를 두지 않음")
    if intent != "none" and not gold:
        raise ValueError(f"{label}: gold_sources가 필요함")
    if intent != "none" and not key_points:
        raise ValueError(f"{label}: key_points가 필요함")
    return EvalItem(label, question, intent, tuple(gold), key_points)


def load_items(path: Path) -> list[EvalItem]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    # 최상위가 목록이어야 함
    if not isinstance(raw, list):
        raise ValueError("평가셋 최상위는 목록이어야 함")

    items = [_item(r, i) for i, r in enumerate(raw)]
    ids = [it.id for it in items]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise ValueError(f"id 중복: {dupes}")
    return items


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_frozen(questions: Path, frozen: Path) -> None:
    if frozen.exists() and frozen.read_text(encoding="utf-8").strip() != sha256_of(questions):
        raise ValueError("평가셋이 동결 이후 변경됨 — 비교표가 성립하지 않음 (eval/README.md 참고)")


def freeze(questions: Path, frozen: Path, force: bool = False) -> str:
    if frozen.exists() and not force:
        raise FileExistsError(f"{frozen} 이미 있음 — 다시 동결하려면 --force")
    digest = sha256_of(questions)
    frozen.write_text(digest + "\n", encoding="utf-8")
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m evaluation.dataset")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    items = load_items(QUESTIONS)
    if args.freeze:
        print(f"동결: {len(items)}문항, sha256 {freeze(QUESTIONS, FROZEN, force=args.force)}")
    else:
        check_frozen(QUESTIONS, FROZEN)
        print(f"검증 통과: {len(items)}문항")
