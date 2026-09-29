"""평가셋 로드·검증·동결 — 설계 §6. SoT는 eval/questions.yaml."""

import argparse
import hashlib
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
    label = str(raw.get("id") or f"#{index}")
    question = str(raw.get("question") or "").strip()
    intent = raw.get("intent")
    if not question:
        raise ValueError(f"{label}: question이 비어 있음")
    if intent not in INTENTS:
        raise ValueError(f"{label}: intent는 {sorted(INTENTS)} 중 하나")
    gold = []
    for g in raw.get("gold_sources") or []:
        page = g.get("page")
        if not isinstance(page, int) or page < 1:
            raise ValueError(f"{label}: gold_sources의 page는 1 이상의 정수")
        gold.append(GoldSource(str(g["file"]), page))
    key_points = tuple(str(k) for k in raw.get("key_points") or [])
    if intent == "none" and gold:
        raise ValueError(f"{label}: intent none에는 gold_sources를 두지 않음")
    if intent != "none" and not gold:
        raise ValueError(f"{label}: gold_sources가 필요함")
    if intent != "none" and not key_points:
        raise ValueError(f"{label}: key_points가 필요함")
    return EvalItem(label, question, intent, tuple(gold), key_points)


def load_items(path: Path) -> list[EvalItem]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or []
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


def freeze(questions: Path, frozen: Path) -> str:
    digest = sha256_of(questions)
    frozen.write_text(digest + "\n", encoding="utf-8")
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="python -m evaluation.dataset")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    items = load_items(QUESTIONS)
    if args.freeze:
        print(f"동결: {len(items)}문항, sha256 {freeze(QUESTIONS, FROZEN)}")
    else:
        check_frozen(QUESTIONS, FROZEN)
        print(f"검증 통과: {len(items)}문항")
