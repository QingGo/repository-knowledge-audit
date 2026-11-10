import numpy as np


def masked_mean(x, mask):
    x = np.asarray(x, dtype=np.float32)
    mask = np.asarray(mask, dtype=bool)
    cnt = mask.sum(axis=1, keepdims=True)
    denom = np.maximum(cnt, 1)
    out = (x * mask[..., None]).sum(axis=1) / denom
    out = out.astype(np.float32)
    out[cnt[:, 0] == 0] = 0
    return out
