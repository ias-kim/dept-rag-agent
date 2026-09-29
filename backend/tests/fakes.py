from app.db.models import EMBEDDING_DIM


def unit(i: int) -> list[float]:
    """i번 축만 1인 단위 벡터. 같은 i끼리 코사인 거리 0, 다른 i끼리 1."""
    v = [0.0] * EMBEDDING_DIM
    v[i % EMBEDDING_DIM] = 1.0
    return v
