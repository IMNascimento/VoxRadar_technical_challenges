import json
from pathlib import Path

import pytest

from kwai_collector.models import Comment, Post

SAMPLES = Path(__file__).parent.parent / "samples"


@pytest.mark.parametrize(
    ("file", "model"),
    [("busca.json", Post), ("usuario.json", Post), ("comentarios.json", Comment)],
)
def test_sample_segue_o_schema(file, model):
    items = json.loads((SAMPLES / file).read_text(encoding="utf-8"))
    assert items
    for item in items:
        model.model_validate(item)
