"""Official piecewise-linear embeddings with reference-consistent ensembling."""
from __future__ import annotations
import torch
from torch import nn


def fit_numeric_bins(training_x: torch.Tensor, n_bins: int=16) -> list[torch.Tensor]:
    """Training data only; constant coordinates get a harmless two-knot map."""
    x=training_x.detach().cpu().float()
    quantiles=torch.linspace(0,1,n_bins+1)
    result=[]
    for j in range(x.shape[1]):
        values=x[:,j][torch.isfinite(x[:,j])]
        if not len(values): knots=torch.tensor([-1.,1.])
        else:
            knots=torch.unique(torch.quantile(values,quantiles),sorted=True)
            if len(knots)<2:knots=torch.tensor([float(knots[0])-1.,float(knots[0])+1.])
        result.append(knots)
    return result


class EmbeddedReferenceModel(nn.Module):
    """A matched TabM baseline or shared log-capacity potential.

    The potential version learns rather than fixes the weights of local charge
    increments. An explicit linear component plus an ensemble residual represent
    a semiparametric degradation potential. No constant proportionality between
    partial and full capacity is assumed.
    """
    def __init__(self,dimension:int,bins:list[torch.Tensor],width:int=96,k:int=8,reference_mode:bool=True):
        super().__init__()
        from tabm import TabM
        from rtdl_num_embeddings import PiecewiseLinearEmbeddings
        self.reference_mode=reference_mode
        din=dimension if reference_mode else 3*dimension+1
        embeddings=PiecewiseLinearEmbeddings(bins,d_embedding=8,activation=False,version='B')
        self.net=TabM.make(n_num_features=din,num_embeddings=embeddings,d_out=1,n_blocks=2,d_block=width,dropout=.05 if not reference_mode else 0.,k=k)
        if reference_mode:
            self.linear=nn.Linear(dimension,1,bias=False)
            nn.init.zeros_(self.linear.weight)
            nn.init.zeros_(self.net.output.weight)
            nn.init.zeros_(self.net.output.bias)
    def forward(self,x,r,lq):
        if not self.reference_mode:
            return self.net(torch.cat([x,r,x-r,lq[:,None]],dim=-1)).squeeze(-1)
        z=torch.cat([x,r],dim=0)
        p=self.net(z).squeeze(-1)*.1+self.linear(z)*.1
        current,reference=p.chunk(2,dim=0)
        return current-reference
