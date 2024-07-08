import random
import torch
import torch.nn as nn

class MixStyle(nn.Module):
    """Based on MixStyle.
    https://github.com/KaiyangZhou/Dassl.pytorch/blob/master/dassl/modeling/ops/mixstyle.py
    Reference:
      Zhou et al. Domain Generalization with MixStyle. ICLR 2021.
    """

    def __init__(self, p=0.5, alpha=0.1, eps=1e-6, mix="random"):
        """
        Args:
          p (float): probability of using MixStyle.
          alpha (float): parameter of the Beta distribution.
          eps (float): scaling parameter to avoid numerical issues.
          mix (str): how to mix.
        """
        super().__init__()
        self.p = p
        self.beta = torch.distributions.Beta(alpha, alpha)
        self.eps = eps
        self.alpha = alpha
        self.mix = mix
        self._activated = True

    def __repr__(self):
        return (
            f"MixStyle(p={self.p}, alpha={self.alpha}, eps={self.eps}, mix={self.mix})"
        )

    def set_activation_status(self, status=True):
        self._activated = status

    def update_mix_method(self, mix="random"):
        self.mix = mix

    def forward(self, x, labels=None):
        if not self.training or not self._activated:
            return x

        if random.random() > self.p:
            return x

        B = x.size(0)

        mu = x.mean(dim=[2, 3], keepdim=True)
        var = x.var(dim=[2, 3], keepdim=True)
        sig = (var + self.eps).sqrt()
        mu, sig = mu.detach(), sig.detach()
        x_normed = (x-mu) / sig

        lmda = self.beta.sample((B, 1, 1, 1))
        lmda = lmda.to(x.device)

        if self.mix == "random":
            # random shuffle
            perm = torch.randperm(B)

        elif self.mix == "crossdomain":
            # split into two halves and swap the order
            perm = torch.arange(B - 1, -1, -1)  # inverse index
            perm_b, perm_a = perm.chunk(2)
            perm_b = perm_b[torch.randperm(perm_b.shape[0])]
            perm_a = perm_a[torch.randperm(perm_a.shape[0])]
            perm = torch.cat([perm_b, perm_a], 0)
        #######################
        #        Added
        #######################
        elif self.mix == "crosssample":
            assert labels != None, 'Label is None'
            contrast_3d = (labels.long()  == 0).nonzero(as_tuple=True)[0]  # find 3d mask attack
            contrast_bf = (labels.long() == 1).nonzero(as_tuple=True)[0] # find bonafide
            contrast_print = (labels.long() == 2).nonzero(as_tuple=True)[0] # find print attack
            contrast_cut = (labels.long() == 3).nonzero(as_tuple=True)[0] # find paper cut attack
            contrast_replay = (labels.long() == 4).nonzero(as_tuple=True)[0] # find replay attack

            perm_idx_3d = contrast_3d[torch.randperm(len(contrast_3d))]
            perm_idx_bf = contrast_bf[torch.randperm(len(contrast_bf))]
            perm_idx_print = contrast_print[torch.randperm(len(contrast_print))]
            perm_idx_cut = contrast_cut[torch.randperm(len(contrast_cut))]
            perm_idx_replay = contrast_replay[torch.randperm(len(contrast_replay))]

            old_idx = torch.cat([contrast_bf, contrast_3d, contrast_print, contrast_cut, contrast_replay], 0)
            perm = torch.cat([perm_idx_bf, perm_idx_3d, perm_idx_print, perm_idx_cut, perm_idx_replay], 0)
            perm = perm[torch.argsort(old_idx)]

        else:
            raise NotImplementedError

        mu2, sig2 = mu[perm], sig[perm]
        mu_mix = mu*lmda + mu2 * (1-lmda)
        sig_mix = sig*lmda + sig2 * (1-lmda)

        return x_normed*sig_mix + mu_mix
