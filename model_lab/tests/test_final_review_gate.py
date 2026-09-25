import pytest
from model_lab.scripts.evaluate_frozen_hybrid import review_gate


def test_final_review_requires_independent_reviewer():
    with pytest.raises(ValueError):
        review_gate({'status':'passed'}, {'package_manifest_sha256':'a'})


def test_final_review_rejects_stale_binding():
    receipt={'status':'passed','independent_reviewer':'audit','package_manifest_sha256':'old'}
    with pytest.raises(ValueError,match='binding'):
        review_gate(receipt, {'package_manifest_sha256':'new'})


def test_final_review_accepts_exact_binding_only():
    receipt={'status':'passed','independent_reviewer':'audit','package_manifest_sha256':'a'}
    review_gate(receipt, {'package_manifest_sha256':'a'})
