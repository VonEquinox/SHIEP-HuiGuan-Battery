"""Capacity-calibrated shared potentials; capacities are labels, not inputs."""
from __future__ import annotations
import torch
from torch import nn

class CapacityCalibratedPotential(nn.Module):
    def __init__(self,dimension:int,width:int=96,k:int=8):
        super().__init__()
        from tabm import TabM
        self.net=TabM.make(n_num_features=dimension,d_out=1,n_blocks=2,d_block=width,dropout=0.,k=k)
    def paired(self,x:torch.Tensor,r:torch.Tensor):
        z=self.net(torch.cat([x,r],dim=0)).squeeze(-1)
        return z.chunk(2,dim=0)
    def forward(self,x,r):
        current,reference=self.paired(x,r)
        return current-reference
