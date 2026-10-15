"""The SocialArb rename keeps old setups working."""
from app.core import paths


def test_new_env_names_win_and_old_names_still_work(tmp_path, monkeypatch):
    monkeypatch.delenv("SOCIALARB_DATA_DIR", raising=False)
    monkeypatch.setenv("CTM_DATA_DIR", str(tmp_path / "old"))
    assert paths.data_dir() == tmp_path / "old"
    monkeypatch.setenv("SOCIALARB_DATA_DIR", str(tmp_path / "new"))
    assert paths.data_dir() == tmp_path / "new"


def test_existing_ctm_database_keeps_being_used(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCIALARB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SOCIALARB_DATABASE_URL", raising=False)
    monkeypatch.delenv("CTM_DATABASE_URL", raising=False)
    assert paths.database_file() == tmp_path / "socialarb.db"       # fresh install
    (tmp_path / "ctm.db").write_bytes(b"")
    assert paths.database_file() == tmp_path / "ctm.db"             # upgraded install keeps its data
    (tmp_path / "socialarb.db").write_bytes(b"")
    assert paths.database_file() == tmp_path / "socialarb.db"       # once rebuilt, the new file wins
