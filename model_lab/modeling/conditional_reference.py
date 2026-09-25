"""Reference-conditioned degradation potentials, not global separability.

Partial observations need not identify full capacity independent of a cell's
initial calibration. Require identity at that calibration, but do not impose
cross-cell transitivity with inconsistent reference contexts.
"""
from __future__ import annotations
import torch
from torch import nn

class ConditionalTabMPotential(nn.Module):
    def __init__(self,dimension:int,width:int=96,k:int=8):
        super().__init__()
        from tabm import TabM
        self.net=TabM.make(n_num_features=dimension*3,d_out=1,n_blocks=2,d_block=width,dropout=0.,k=k)
    def potential(self,x,context):
        return self.net(torch.cat([x,context,x-context],dim=-1)).squeeze(-1)
    def paired(self,x,r):
        n=len(x)
        z=self.potential(torch.cat([x,r],dim=0),torch.cat([r,r],dim=0))
        return z[:n],z[n:]
    def forward(self,x,r):
        a,b=self.paired(x,r)
        return a-b

class FiLMReferencePotential(nn.Module):
    def __init__(self,dimension:int,width:int=96,k:int=8,use_context:bool=True):
        super().__init__()
        self.k,self.width,self.use_context=k,width,use_context
        self.stem=nn.Linear(dimension,width)
        self.hidden=nn.Linear(width,width)
        self.context=nn.Sequential(nn.Linear(dimension,32),nn.GELU(),nn.Linear(32,4*width))
        nn.init.zeros_(self.context[-1].weight);nn.init.zeros_(self.context[-1].bias)
        self.fast_r=nn.Parameter(torch.empty(k,width));self.fast_s=nn.Parameter(torch.empty(k,width))
        nn.init.normal_(self.fast_r,1.,.15);nn.init.normal_(self.fast_s,1.,.15)
        self.output=nn.Parameter(torch.empty(k,width));nn.init.normal_(self.output,0.,width**-.5)
        self.bias=nn.Parameter(torch.zeros(k))
    def potential(self,x,context):
        if self.use_context:
            g1,b1,g2,b2=self.context(context).chunk(4,dim=-1)
            g1,g2=1+.3*torch.tanh(g1),1+.3*torch.tanh(g2)
            b1,b2=.3*b1,.3*b2
        else:
            g1=g2=torch.ones((len(x),self.width),device=x.device,dtype=x.dtype)
            b1=b2=torch.zeros_like(g1)
        h=torch.nn.functional.gelu(self.stem(x)*g1+b1)
        h=h[:,None,:]*self.fast_r[None,:,:]
        h=torch.nn.functional.gelu(self.hidden(h)*g2[:,None,:]+b2[:,None,:])
        h=h*self.fast_s[None,:,:]
        return (h*self.output[None,:,:]).sum(-1)+self.bias
    def paired(self,x,r):
        n=len(x)
        p=self.potential(torch.cat([x,r],dim=0),torch.cat([r,r],dim=0))
        return p[:n],p[n:]
    def forward(self,x,r):
        a,b=self.paired(x,r);return a-b
