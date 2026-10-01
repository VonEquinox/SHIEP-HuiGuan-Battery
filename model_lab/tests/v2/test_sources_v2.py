import hashlib
from pathlib import Path
import pytest
from model_lab.modeling.v2 import sources


class Response:
    def __init__(self, content, status=200, headers=None):
        self.content = content
        self.status_code = status
        self.headers = headers or {}
        self.url = "https://official.example/measurement.mat"
    def raise_for_status(self):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *_):
        pass
    def iter_content(self, size):
        yield self.content


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append(kwargs)
        return self.response
    def close(self):
        pass


def test_resume_verifies_author_checksum_before_atomic_finalize(tmp_path, monkeypatch):
    payload = b"0123456789"
    output = tmp_path / "raw.mat"
    output.with_name("raw.mat.part").write_bytes(payload[:4])
    session = Session(Response(payload[4:], 206, {"Content-Range": "bytes 4-9/10"}))
    monkeypatch.setattr(sources, "_session", lambda _: session)
    result = sources.download_verified({"name": "raw.mat", "url": "https://official.example/measurement.mat", "bytes": len(payload), "author_checksum": "md5:" + hashlib.md5(payload).hexdigest()}, output)
    assert output.read_bytes() == payload and result["status"] == "verified"
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()
    assert session.calls[0]["headers"]["Range"] == "bytes=4-"
    assert not output.with_name("raw.mat.part").exists()


def test_mismatched_checksum_retains_failed_attempt(tmp_path, monkeypatch):
    output = tmp_path / "raw.mat"
    monkeypatch.setattr(sources, "_session", lambda _: Session(Response(b"wrong")))
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        sources.download_verified({"url": "https://official.example/measurement.mat", "bytes": 5, "author_checksum": "md5:" + "0" * 32}, output, retries=1)
    assert not output.exists()
    assert output.with_name("raw.mat.part.checksum-failed-0").exists()


def test_download_budget_and_scheme_fail_before_network(tmp_path):
    with pytest.raises(ValueError, match="budget"):
        sources.download_verified({"url": "https://official.example/raw", "bytes": 100}, tmp_path / "raw", max_bytes=10)
    with pytest.raises(ValueError, match="HTTPS"):
        sources.download_verified({"url": "file:///etc/passwd"}, tmp_path / "raw")


def test_dyad_declarative_decoder_denies_executable_global():
    from model_lab.modeling.v2.sources import decode_dyad_numeric_archive
    with pytest.raises(ValueError, match="global rejected"):
        decode_dyad_numeric_archive(b"cos\nsystem\n(S'echo forbidden'\ntR.")


def test_dyad_declarative_numeric_roundtrip():
    import pickle
    import numpy as np
    from model_lab.modeling.v2.sources import decode_dyad_numeric_archive
    expected = np.arange(12, dtype=np.float64).reshape(3, 4)
    values, metadata = decode_dyad_numeric_archive(pickle.dumps((expected, {"car": 1, "charge_segment": "2"}), protocol=2))
    assert np.array_equal(values, expected) and metadata["car"] == 1
