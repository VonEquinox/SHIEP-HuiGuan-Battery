import torch
from model_lab.modeling.conditional_reference import ConditionalTabMPotential,FiLMReferencePotential
from model_lab.modeling.capacity_calibrated import CapacityCalibratedPotential

def test_identity_and_fixed_context_composition():
    for model in [ConditionalTabMPotential(4,16,4),FiLMReferencePotential(4,16,4,True),FiLMReferencePotential(4,16,4,False)]:
        model.eval();x,r,z,c=torch.randn(4,5,4)
        torch.testing.assert_close(model(x,x),torch.zeros(5,4),atol=1e-6,rtol=1e-6)
        hx,hr,hz=model.potential(x,c),model.potential(r,c),model.potential(z,c)
        torch.testing.assert_close((hx-hr)+(hr-hz),hx-hz,atol=1e-6,rtol=1e-6)
        model(x,r).square().mean().backward()
        assert any(p.grad is not None for p in model.parameters())

def test_context_really_changes_mapping_not_only_output_offset():
    m=FiLMReferencePotential(4,16,4,True)
    with torch.no_grad():
        m.context[-1].weight.normal_(0,.1)
    x,z,c,d=torch.randn(4,5,4)
    a=m.potential(x,c)-m.potential(z,c)
    b=m.potential(x,d)-m.potential(z,d)
    assert not torch.allclose(a,b,atol=1e-6)

def test_absolute_supervised_backbone_still_has_exact_reference_identity():
    m=CapacityCalibratedPotential(4,16,4);x=torch.randn(5,4)
    torch.testing.assert_close(m(x,x),torch.zeros(5,4),atol=1e-6,rtol=1e-6)

def test_toy_offset_observation_rejects_global_cross_context_transitivity():
    # If x=a+health and reference r=a+1, health=1+x-r.
    # These pairs have DIFFERENT cell calibration contexts; forcing a global
    # potential implies a false multiplicative composition constraint.
    x,r,z=.8,1.,1.2
    assert abs((1+x-r)*(1+r-z)-(1+x-z))>.01
