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
    args = parser.parse_args(argv)
    with Session(make_engine()) as session:
        report = sync_folder(
            session, args.root, OpenAIEmbedder.from_settings(settings),
            max_chars=settings.chunk_max_chars, overlap=settings.chunk_overlap,
        )
    print(report.summary())


if __name__ == "__main__":
    main()
