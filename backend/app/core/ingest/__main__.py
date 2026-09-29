import argparse
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.embeddings import OpenAIEmbedder
from app.core.ingest.sync import sync_folder
from app.db.session import make_engine


def main(argv: list[str] | None = None) -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(prog="python -m app.core.ingest")
    parser.add_argument("--root", type=Path, default=settings.data_dir)
    parser.add_argument("--prune", action="store_true", help="폴더가 비었거나 스코프 폴더가 없어도 색인을 삭제")
    args = parser.parse_args(argv)
    with Session(make_engine()) as session:
        report = sync_folder(
            session, args.root, OpenAIEmbedder.from_settings(settings),
            max_chars=settings.chunk_max_chars, overlap=settings.chunk_overlap, prune=args.prune,
            strategy=settings.chunk_strategy,
        )
    print(report.summary())


if __name__ == "__main__":
    main()
