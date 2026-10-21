from pathlib import Path

import pytest

from subforest import TreeStore
from subforest.cli import main


def test_build_creates_db(corpus_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "corpus.db"
    assert main(["build", str(corpus_dir), "--db", str(db), "--corpus-id", "larch"]) == 0
    assert "12 docs" in capsys.readouterr().out
    with TreeStore(db) as store:
        assert [n.title for n in store.roots()] == ["larch/"]


def test_build_refuses_existing_db_without_force(corpus_dir: Path, tmp_path: Path) -> None:
    db = tmp_path / "corpus.db"
    db.write_text("")
    assert main(["build", str(corpus_dir), "--db", str(db)]) == 2
    assert main(["build", str(corpus_dir / "sitemap.xml"), "--db", str(db), "--force"]) == 0
