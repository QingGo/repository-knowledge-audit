import numpy as np


def masked_mean(x, mask):
    return x.mean(axis=1)
