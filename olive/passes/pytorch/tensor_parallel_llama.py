# -------------------------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
# --------------------------------------------------------------------------
# Automatically distribute HF Llama model using Tensor Parallelism
# --------------------------------------------------------------------------

import logging
import math
from typing import Any, Dict, Optional, Tuple

import torch
import torch.nn.functional as F
from tensor_parallel_layers import TensorParallelColumnLinear, TensorParallelRowLinear
from transformers.activations import ACT2FN
from transformers.models.llama.modeling_llama import LlamaAttention, LlamaMLP, repeat_kv, rotate_half

from olive.model import DistributedPyTorchModel, PyTorchModel
from olive.passes import Pass

logger = logging.getLogger(__name__)


# Tensor Parallel layers. This layers will replace corresponding layer in the model.
def tp_llama_mlp_init(self, config):
    super(LlamaMLP, self).__init__()
    self.config = config
    self.hidden_size = config.hidden_size
    self.intermediate_size = config.intermediate_size

    # Original
    # self.gate_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)
    # self.up_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)
    # self.down_proj = nn.Linear(self.intermediate_size, self.hidden_size, bias=False)
    self.gate_proj = TensorParallelColumnLinear(self.hidden_size, self.intermediate_size, bias=False)
    self.up_proj = TensorParallelColumnLinear(self.hidden_size, self.intermediate_size, bias=False)
    self.down_proj = TensorParallelRowLinear(self.intermediate_size, self.hidden_size, bias=False)

    self.act_fn = ACT2FN[config.hidden_act]


def tp_llama_attention_init(self, config):
    super(LlamaAttention, self).__init__()
    self.config = config
    self.hidden_size = config.hidden_size
    self.num_heads = config.num_attention_heads
    self.head_dim = self.hidden_size // self.num_heads
    self.num_key_value_heads = config.num_key_value_heads
    self.num_key_value_groups = self.num_heads // self.num_key_value_heads
    self.max_position_embeddings = config.max_position_embeddings
    self.rope_theta = config.rope_theta

    if (self.head_dim * self.num_heads) != self.hidden_size:
        raise ValueError(
            f"hidden_size must be divisible by num_heads (got `hidden_size`: {self.hidden_size}"
            f" and `num_heads`: {self.num_heads})."
        )

    # Original
    # self.q_proj = nn.Linear(self.hidden_size, self.num_heads * self.head_dim, bias=False)
    # self.k_proj = nn.Linear(self.hidden_size, self.num_key_value_heads * self.head_dim, bias=False)
    # self.v_proj = nn.Linear(self.hidden_size, self.num_key_value_heads * self.head_dim, bias=False)
    # self.o_proj = nn.Linear(self.num_heads * self.head_dim, self.hidden_size, bias=False)
    self.q_proj = TensorParallelColumnLinear(self.hidden_size, self.num_heads * self.head_dim, bias=False)
    self.k_proj = TensorParallelColumnLinear(self.hidden_size, self.num_key_value_heads * self.head_dim, bias=False)
    self.v_proj = TensorParallelColumnLinear(self.hidden_size, self.num_key_value_heads * self.head_dim, bias=False)
    self.o_proj = TensorParallelRowLinear(self.num_heads * self.head_dim, self.hidden_size, bias=False)

    self._init_rope()


# Overwrite original functions
def apply_rotary_pos_emb(q, k, cos, sin, position_ids):
    # The first two dimensions of cos and sin are always 1, so we can `squeeze` them.

    # Original
    # cos = cos.squeeze(1).squeeze(0)  # [seq_len, dim]
    # sin = sin.squeeze(1).squeeze(0)  # [seq_len, dim]
    # Workaround: rewrite the above to avoid exporting `If` node
    cos = cos.reshape(cos.shape[2], cos.shape[3])
    sin = sin.reshape(sin.shape[2], sin.shape[3])

    cos = cos[position_ids].unsqueeze(1)  # [bs, 1, seq_len, dim]
    sin = sin[position_ids].unsqueeze(1)  # [bs, 1, seq_len, dim]
    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed


def tp_llama_attention_forward(
    self,
    hidden_states: torch.Tensor,
    attention_mask: Optional[torch.Tensor] = None,
    position_ids: Optional[torch.LongTensor] = None,
    past_key_value: Optional[Tuple[torch.Tensor]] = None,
    output_attentions: bool = False,
    use_cache: bool = False,
) -> Tuple[torch.Tensor, Optional[torch.Tensor], Optional[Tuple[torch.Tensor]]]:
    bsz, q_len, _ = hidden_states.size()

    if self.config.pretraining_tp > 1:
        key_value_slicing = (self.num_key_value_heads * self.head_dim) // self.config.pretraining_tp
        query_slices = self.q_proj.weight.split((self.num_heads * self.head_dim) // self.config.pretraining_tp, dim=0)
        key_slices = self.k_proj.weight.split(key_value_slicing, dim=0)
        value_slices = self.v_proj.weight.split(key_value_slicing, dim=0)

        query_states = [F.linear(hidden_states, query_slices[i]) for i in range(self.config.pretraining_tp)]
        query_states = torch.cat(query_states, dim=-1)

        key_states = [F.linear(hidden_states, key_slices[i]) for i in range(self.config.pretraining_tp)]
        key_states = torch.cat(key_states, dim=-1)

        value_states = [F.linear(hidden_states, value_slices[i]) for i in range(self.config.pretraining_tp)]
        value_states = torch.cat(value_states, dim=-1)

    else:
        query_states = self.q_proj(hidden_states)
        key_states = self.k_proj(hidden_states)
        value_states = self.v_proj(hidden_states)

    query_states = query_states.view(bsz, q_len, self.num_heads, self.head_dim).transpose(1, 2)
    key_states = key_states.view(bsz, q_len, self.num_key_value_heads, self.head_dim).transpose(1, 2)
    value_states = value_states.view(bsz, q_len, self.num_key_value_heads, self.head_dim).transpose(1, 2)

    kv_seq_len = key_states.shape[-2]
    if past_key_value is not None:
        kv_seq_len += past_key_value[0].shape[-2]

    cos, sin = self.rotary_emb(value_states, seq_len=kv_seq_len)
    query_states, key_states = apply_rotary_pos_emb(query_states, key_states, cos, sin, position_ids)

    if past_key_value is not None:
        # reuse k, v, self_attention
        key_states = torch.cat([past_key_value[0], key_states], dim=2)
        value_states = torch.cat([past_key_value[1], value_states], dim=2)

    past_key_value = (key_states, value_states) if use_cache else None

    # repeat k/v heads if n_kv_heads < n_heads
    key_states = repeat_kv(key_states, self.num_key_value_groups)
    value_states = repeat_kv(value_states, self.num_key_value_groups)

    attn_weights = torch.matmul(query_states, key_states.transpose(2, 3)) / math.sqrt(self.head_dim)

    if attn_weights.size() != (bsz, self.num_heads, q_len, kv_seq_len):
        raise ValueError(
            f"Attention weights should be of size {(bsz, self.num_heads, q_len, kv_seq_len)}, but is"
            f" {attn_weights.size()}"
        )

    if attention_mask is not None:
        if attention_mask.size() != (bsz, 1, q_len, kv_seq_len):
            raise ValueError(
                f"Attention mask should be of size {(bsz, 1, q_len, kv_seq_len)}, but is {attention_mask.size()}"
            )
        attn_weights = attn_weights + attention_mask

    # upcast attention to fp32
    attn_weights = torch.nn.functional.softmax(attn_weights, dim=-1, dtype=torch.float32).to(query_states.dtype)
    attn_output = torch.matmul(attn_weights, value_states)

    if attn_output.size() != (bsz, self.num_heads, q_len, self.head_dim):
        raise ValueError(
            f"`attn_output` should be of size {(bsz, self.num_heads, q_len, self.head_dim)}, but is"
            f" {attn_output.size()}"
        )

    attn_output = attn_output.transpose(1, 2).contiguous()
    # Original
    # attn_output = attn_output.reshape(bsz, q_len, self.hidden_size)
    attn_output = attn_output.reshape(bsz, q_len, -1)

    if self.config.pretraining_tp > 1:
        attn_output = attn_output.split(self.hidden_size // self.config.pretraining_tp, dim=2)
        o_proj_slices = self.o_proj.weight.split(self.hidden_size // self.config.pretraining_tp, dim=1)
        attn_output = sum([F.linear(attn_output[i], o_proj_slices[i]) for i in range(self.config.pretraining_tp)])
    else:
        attn_output = self.o_proj(attn_output)

    if not output_attentions:
        attn_weights = None

    return attn_output, attn_weights, past_key_value


def tp_llama_attention_parallel_split(self, r, ws):
    self.num_heads = self.num_heads // ws
    self.num_key_value_heads = self.num_key_value_heads // ws


class LlamaPyTorchTensorParallel(Pass):
    def __init__(self):
        super().__init__()
        self.mlp_init = LlamaMLP.__init__
        self.attention_init = LlamaAttention.__init__
        self.attention_forward = LlamaAttention.forward

    def _run_for_config(
        self, model: PyTorchModel, data_root: str, config: Dict[str, Any], output_model_path: str
    ) -> DistributedPyTorchModel:
        return super()._run_for_config(model, data_root, config, output_model_path)

    def replace_layers(self):
        LlamaMLP.__init__ = tp_llama_mlp_init
        LlamaAttention.__init__ = tp_llama_attention_init
        LlamaAttention.forward = tp_llama_attention_forward
        LlamaAttention.parallel_split = tp_llama_attention_parallel_split

    def restore_layers(self):
        LlamaMLP.__init__ = self.mlp_init
        LlamaAttention.__init__ = self.attention_init
        LlamaAttention.forward = self.attention_forward
        LlamaAttention.parallel_split = None

    def split_weights(self, the_model):
        def _split_model(the_model, ws):
            if isinstance(the_model, (TensorParallelColumnLinear, TensorParallelRowLinear, LlamaAttention)):
                the_model.parallel_split(ws)
            for m in the_model._modules.values():
                _split_model(m, self.world_size)

        _split_model(the_model, self.world_size)

    def load_rank_weights(self, the_model, rank):
        def _load_rank_weights(the_model, r, ws):
            if isinstance(the_model, (TensorParallelColumnLinear, TensorParallelRowLinear, LlamaAttention)):
                the_model.load_rank_weights(r, ws)
            for m in the_model._modules.values():
                _load_rank_weights(m, r, ws)

        _load_rank_weights(the_model, rank, self.world_size)
