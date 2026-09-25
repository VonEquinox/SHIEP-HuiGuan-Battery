import numpy as np
import torch
from model_lab.data.physical_curve_features import curve_features
from model_lab.modeling.embedded_potential import EmbeddedReferenceModel,fit_numeric_bins


def test_physical_view_uses_only_input_and_retains_shape():
    a=np.zeros((2,64,4));a[:,:,0]=np.linspace(0,30,64);a[:,:,1]=np.linspace(0,.5,64);a[:,:,2]=1
    x=np.concatenate([a.reshape(2,-1),np.ones((2,256))],axis=1)
    f=curve_features(x)
    assert f.shape==(2,69)
    np.testing.assert_allclose(f[:,16:32].sum(axis=1),1,atol=1e-6)
    a[:,:,1]*=2
    y=np.concatenate([a.reshape(2,-1),np.ones((2,256))],axis=1)
    g=curve_features(y)
    np.testing.assert_allclose(g[:,:16]-f[:,:16],np.log(2),rtol=1e-6)
    np.testing.assert_allclose(g[:,16:32],f[:,16:32])


def test_embedded_potential_exact_consistency_and_training_bins():
    torch.manual_seed(10)
    training=torch.randn(30,4);training[:,3]=0
    bins=fit_numeric_bins(training)
    model=EmbeddedReferenceModel(4,bins,width=16,k=4,reference_mode=True)
    with torch.no_grad():
        for p in model.parameters():p.add_(.02*torch.randn_like(p))
    model.eval();a,b,c=torch.randn(3,5,4);q=torch.randn(3,5)
    ab=model(a,b,q[0]-q[1]);bc=model(b,c,q[1]-q[2]);ac=model(a,c,q[0]-q[2])
    torch.testing.assert_close(ab+bc,ac,atol=1e-6,rtol=1e-6)
    torch.testing.assert_close(model(a,a,torch.zeros(5)),torch.zeros_like(ab),atol=1e-6,rtol=1e-6)
    loss=ac.square().mean();loss.backward()
    assert any(p.grad is not None for p in model.parameters())
