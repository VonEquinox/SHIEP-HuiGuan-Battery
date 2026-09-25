"""Small synthetic unit fixtures, never used as reported battery experiments."""

import pytest
import torch

from model_lab.modeling.cada import CADA, TargetScaledRegressor
from model_lab.scripts import data_cli


def test_target_scaling_is_serialized_and_differentiable(tmp_path):
    model = TargetScaledRegressor(CADA(3), 0.91, 0.05)
    x = [torch.randn(2, 3), torch.randn(2, 3), torch.randn(2, 8, 3), torch.ones(2, 8), torch.ones(2, 1)]
    loss = ((model(*x) - 0.9) / 0.05).square().mean()
    loss.backward()
    assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)
    path = tmp_path / "own-fixture.pt"
    torch.save(model.state_dict(), path)
    restored = TargetScaledRegressor(CADA(3), 0.0, 1.0)
    restored.load_state_dict(torch.load(path, weights_only=True))
    assert torch.allclose(model(*x), restored(*x), atol=1e-6)
    assert torch.isclose(restored.target_mean, torch.tensor(0.91))


@pytest.mark.parametrize("status,headers,body", [
    (200, {}, b"whole-response"),
    (206, {"Content-Range": "bytes 0-5/6"}, b"wrong-start"),
    (206, {"Content-Range": "bytes 3-5/6"}, b"too-many-bytes"),
])
def test_invalid_resume_preserves_existing_partial(tmp_path, monkeypatch, status, headers, body):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            return body

    response = Response()
    response.status, response.headers = status, headers
    monkeypatch.setattr(data_cli, "ROOT", tmp_path)
    monkeypatch.setattr(data_cli, "MAX_RETRIES", 1)
    monkeypatch.setattr(data_cli, "load_registry", lambda: {"disk_policy": {"max_new_bytes": 1000, "min_free_bytes": 100}})
    monkeypatch.setattr(data_cli, "free_bytes", lambda path: 10000)
    monkeypatch.setattr(data_cli, "event", lambda *args, **kwargs: None)
    monkeypatch.setattr(data_cli.urllib.request, "urlopen", lambda *args, **kwargs: response)
    target = tmp_path / "fixture.zip"
    partial = tmp_path / "fixture.zip.part"
    partial.write_bytes(b"abc")
    with pytest.raises(IOError):
        data_cli.download_file("https://example.invalid/data", target, 6, None, "test")
    assert partial.read_bytes() == b"abc"

