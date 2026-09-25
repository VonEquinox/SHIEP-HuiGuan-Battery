import numpy as np
import torch
from model_lab.modeling.reference_potential import ReferencePotential, TabMReferencePotential, cell_centered_pair_loss
from model_lab.scripts.train_reference_cv import DifferenceKernel, transform_fit, weights


def check_identities(model):
    model.eval()
    # Nonzero weights ensure this tests a learned correction, not only the prior.
    with torch.no_grad():
        for p in model.parameters(): p.add_(torch.randn_like(p)*.03)
    a,b,c=torch.randn(3,5,4)
    logq=torch.randn(3,5)*.2
    ab=model(a,b,logq[0]-logq[1])
    bc=model(b,c,logq[1]-logq[2])
    ac=model(a,c,logq[0]-logq[2])
    ba=model(b,a,logq[1]-logq[0])
    identity=model(a,a,torch.zeros(5))
    torch.testing.assert_close(identity,torch.zeros_like(identity),atol=1e-6,rtol=1e-6)
    torch.testing.assert_close(ab,-ba,atol=1e-6,rtol=1e-6)
    torch.testing.assert_close(ab+bc,ac,atol=1e-6,rtol=1e-6)
    return ac


def test_mlp_reference_identity_and_transitivity():
    check_identities(ReferencePotential(4,width=16))


def test_official_tabm_reference_identity_and_transitivity():
    out=check_identities(TabMReferencePotential(4,width=16,k=4))
    assert out.shape==(5,4)


def test_linear_time_all_pair_loss():
    e=torch.tensor([.1,.2,.4,-.2,.5],requires_grad=True)
    cell=torch.tensor([0,0,0,1,1])
    expected=[]
    for k in (0,1):
        x=e[cell==k];n=len(x)
        pairs=sum((x[i]-x[j])**2 for i in range(n) for j in range(i+1,n))
        expected.append(pairs/n**2)
    torch.testing.assert_close(cell_centered_pair_loss(e,cell),torch.stack(expected).mean())


def test_difference_kernel_positive_semidefinite_and_reference_identity():
    rng=np.random.default_rng(5);x=rng.normal(size=(15,4));r=rng.normal(size=(15,4))
    model=DifferenceKernel(alpha=.1,gamma=.2)
    k=model.kernel(x,r,x,r)
    assert np.linalg.eigvalsh(k).min()>-1e-9
    model.fit(x,r,np.zeros(15),rng.normal(size=15),np.ones(15))
    np.testing.assert_allclose(model.predict(x,x,np.zeros(15)),0,atol=1e-9)


def test_preprocessing_does_not_fit_validation_statistics():
    x=np.array([[1.,2.],[3.,4.],[100.,200.]],dtype=np.float32);r=x/2
    sx,_,s=transform_fit(x,r,np.array([0,1]))
    y=x.copy();y[2]=1e8
    sy,_,t=transform_fit(y,r,np.array([0,1]))
    np.testing.assert_array_equal(s['mean'],t['mean'])
    np.testing.assert_array_equal(sx[:2],sy[:2])
    w=weights(np.array(['a','a','b']))
    assert np.isclose(w[:2].sum(),w[2])
