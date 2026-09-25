"""Reference-consistent SOH models. Research hypotheses, not SOTA claims.
Inputs contain observed partial-charge signals only. Full capacity is a label.
"""
from __future__ import annotations
import torch
from torch import nn

class CurrentMLP(nn.Module):
    def __init__(self, dimension:int, width:int=96):
        super().__init__()
        self.net=nn.Sequential(nn.Linear(dimension,width),nn.GELU(),nn.Linear(width,width),nn.GELU(),nn.Linear(width,1))
    def forward(self,current,reference,log_window_ratio):
        return self.net(current)

class MatchedMLP(nn.Module):
    def __init__(self, dimension:int, width:int=96):
        super().__init__()
        self.net=nn.Sequential(nn.Linear(dimension*3+1,width),nn.GELU(),nn.Linear(width,width),nn.GELU(),nn.Linear(width,1))
    def forward(self,current,reference,log_window_ratio):
        return self.net(torch.cat((current,reference,current-reference,log_window_ratio[:,None]),dim=-1))

class ReferencePotential(nn.Module):
    """log SOH = log(q_window / q_reference) + g(x) - g(reference).

    No temporal monotonicity is imposed. Shared scalar potential ensures exact
    identity, reversal and transitivity (at deterministic inference). The common
    multiplicative calibration cancels; this is not proof of electrochemical
    mechanism identification or of statistical superiority.
    """
    def __init__(self, dimension:int, width:int=96, physical_prior:bool=True):
        super().__init__()
        self.physical_prior=physical_prior
        self.net=nn.Sequential(nn.Linear(dimension,width),nn.GELU(),nn.Linear(width,width),nn.GELU(),nn.Linear(width,1))
        nn.init.zeros_(self.net[-1].weight)
        nn.init.zeros_(self.net[-1].bias)
    def forward(self,current,reference,log_window_ratio):
        potential=self.net(torch.cat((current,reference),dim=0))*0.1
        x,r=potential.chunk(2,dim=0)
        return x-r+(log_window_ratio[:,None] if self.physical_prior else 0.0)

class TabMDirect(nn.Module):
    """Official TabM backbone on exactly the same matched input information."""
    def __init__(self,dimension:int,width:int=96,k:int=8):
        super().__init__()
        from tabm import TabM
        self.net=TabM.make(n_num_features=dimension*3+1,d_out=1,n_blocks=2,d_block=width,dropout=0.0,k=k)
    def forward(self,current,reference,log_window_ratio):
        x=torch.cat((current,reference,current-reference,log_window_ratio[:,None]),dim=-1)
        return self.net(x).squeeze(-1)

class TabMReferencePotential(nn.Module):
    """Shared TabM potential differences, with geometric ensemble inference.

    Mean log-prediction followed by exp retains exact reference consistency.
    Averaging SOH values arithmetically would not retain exact transitivity.
    """
    def __init__(self,dimension:int,width:int=96,k:int=8):
        super().__init__()
        from tabm import TabM
        self.net=TabM.make(n_num_features=dimension,d_out=1,n_blocks=2,d_block=width,dropout=0.0,k=k)
        nn.init.zeros_(self.net.output.weight)
        nn.init.zeros_(self.net.output.bias)
    def forward(self,current,reference,log_window_ratio):
        p=self.net(torch.cat((current,reference),dim=0)).squeeze(-1)*0.1
        x,r=p.chunk(2,dim=0)
        return x-r+log_window_ratio[:,None]

def cell_centered_pair_loss(error:torch.Tensor,cell:torch.Tensor)->torch.Tensor:
    """Equal-cell mean squared centered error, O(N); no fake N^2 sample count.

    For n errors within one cell:
      sum_{i<j}(e_i-e_j)^2 = n * sum_i(e_i-mean(e))^2.
    The normalized centered error is therefore an all-pair objective without
    allocating all pairs. Labels of training cells only may enter this loss.
    """
    if error.ndim==1: error=error[:,None]
    losses=[]
    for c in torch.unique(cell):
        e=error[cell==c]
        if len(e)>1: losses.append((e-e.mean(dim=0,keepdim=True)).square().mean())
    return torch.stack(losses).mean() if losses else error.sum()*0
