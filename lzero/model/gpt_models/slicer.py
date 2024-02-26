import math
from typing import List

import torch
import torch.nn as nn

class Slicer(nn.Module):
    def __init__(self, max_blocks: int, block_mask: torch.Tensor) -> None:
        super().__init__()
        self.block_size = block_mask.size(0)
        self.num_kept_tokens = block_mask.sum().long().item()
        kept_indices = torch.where(block_mask)[0].repeat(max_blocks)
        offsets = torch.arange(max_blocks).repeat_interleave(self.num_kept_tokens)
        self.indices = kept_indices + block_mask.size(0) * offsets

        print("precompute_slices() begin")
        self.cache = {}
        max_steps = max_blocks * self.block_size # 5*17
        for num_steps in range(max_steps+1):
            for prev_steps in range(max_steps+1):
                total_steps = num_steps + prev_steps
                num_blocks = math.ceil(total_steps / self.block_size) # self.block_size=17
                indices = self.indices[:num_blocks * self.num_kept_tokens]
                result = indices[torch.logical_and(prev_steps <= indices, indices < total_steps)] - prev_steps
                self.cache[(num_steps, prev_steps)] = result
        print("precompute_slices() done")

    def compute_slice(self, num_steps: int, prev_steps: int = 0) -> torch.Tensor:
        return self.cache[(num_steps, prev_steps)]

    def forward(self, *args, **kwargs):
        raise NotImplementedError


class Head(Slicer):
    def __init__(self, max_blocks: int, block_mask: torch.Tensor, head_module: nn.Module) -> None:
        super().__init__(max_blocks, block_mask)
        assert isinstance(head_module, nn.Module)
        self.head_module = head_module

    def forward(self, x: torch.Tensor, num_steps: int, prev_steps: int) -> torch.Tensor:
        if isinstance(prev_steps, torch.Tensor):
            x_sliced = [x[i, self.compute_slice(num_steps, prev_steps[i].item())] for i in range(prev_steps.shape[0])]
            x_sliced =  torch.cat(x_sliced, dim=0)
        elif isinstance(prev_steps, int):
            x_sliced = x[:, self.compute_slice(num_steps, prev_steps)]  # x is (B, T, E)
        return self.head_module(x_sliced)


class Embedder(nn.Module):
    def __init__(self, max_blocks: int, block_masks: List[torch.Tensor], embedding_tables: List[nn.Embedding]) -> None:
        super().__init__()
        assert len(block_masks) == len(embedding_tables)
        assert (sum(block_masks) == 1).all()  # block mask are a partition of a block
        self.embedding_dim = embedding_tables[0].embedding_dim
        assert all([e.embedding_dim == self.embedding_dim for e in embedding_tables])
        self.embedding_tables = embedding_tables
        self.slicers = [Slicer(max_blocks, block_mask) for block_mask in block_masks]

    def forward(self, tokens: torch.Tensor, num_steps: int, prev_steps: int) -> torch.Tensor:
        assert tokens.ndim == 2  # x is (B, T)
        output = torch.zeros(*tokens.size(), self.embedding_dim, device=tokens.device)
        for slicer, emb in zip(self.slicers, self.embedding_tables):
            s = slicer.compute_slice(num_steps, prev_steps)
            output[:, s] = emb(tokens[:, s])
            # try:
            #     output[:, s] = emb(tokens[:, s])
            # except:
            #     print('debug')
        return output

class ActEmbedder(nn.Module):
    def __init__(self, max_blocks: int, block_masks: List[torch.Tensor], embedding_tables: List[nn.Embedding]) -> None:
        super().__init__()
        assert len(block_masks) == len(embedding_tables)
        # assert (sum(block_masks) == 1).all()  # block mask are a partition of a block
        self.embedding_dim = embedding_tables[0].embedding_dim
        assert all([e.embedding_dim == self.embedding_dim for e in embedding_tables])
        self.embedding_tables = embedding_tables
        self.slicers = [Slicer(max_blocks, block_mask) for block_mask in block_masks]

    def forward(self, tokens: torch.Tensor, num_steps: int, prev_steps: int) -> torch.Tensor:
        assert tokens.ndim == 2  # x is (B, T)
        output = torch.zeros(*tokens.size(), self.embedding_dim, device=tokens.device)
        for slicer, emb in zip(self.slicers, self.embedding_tables):
            s = slicer.compute_slice(num_steps, prev_steps)
            output[:, s] = emb(tokens[:, s])
            # try:
            #     output[:, s] = emb(tokens[:, s])
            # except:
            #     print('debug')
        return output