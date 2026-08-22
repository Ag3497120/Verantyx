import mlx.core as mx
import mlx.nn as nn
from dataclasses import dataclass
import math
from ouroboros_mlx import OuroborosResonanceGateMLX

@dataclass
class GPTConfig:
    vocab_size: int = 65536
    n_layer: int = 40
    n_head: int = 40
    n_embd: int = 5120
    head_dim: int = 128

class ActGain(nn.Module):
    def __init__(self, init_value: float):
        super().__init__()
        self.a_g = mx.array([init_value])

    def __call__(self, x: mx.array) -> mx.array:
        return x * self.a_g

def rms_norm(x: mx.array, eps: float = 1e-5) -> mx.array:
    x_f32 = x.astype(mx.float32)
    return (x_f32 * mx.rsqrt(x_f32.square().mean(-1, keepdims=True) + eps)).astype(x.dtype)

class HeadGain(nn.Module):
    def __init__(self, n_head: int):
        super().__init__()
        self.head_g = mx.ones([n_head])

    def __call__(self, x: mx.array) -> mx.array:
        return x * self.head_g.reshape(1, -1, 1, 1)

class WeightGain(nn.Module):
    def __init__(self):
        super().__init__()
        self.w_g = mx.array([1.0])
    def __call__(self, w: mx.array) -> mx.array:
        return w * self.w_g



class CausalSelfAttention(nn.Module):
    def __init__(self, config: GPTConfig):
        super().__init__()
        self.n_head = config.n_head
        self.n_kv_head = config.n_kv_head
        self.head_dim = config.n_embd // config.n_head
        n_state = config.n_embd

        self.attn_query = nn.Linear(n_state, n_state, bias=False)
        self.attn_key = nn.Linear(n_state, n_state, bias=False)
        self.attn_value = nn.Linear(n_state, n_state, bias=False)
        self.attn_resid = nn.Linear(n_state, n_state, bias=False)
        self.head_gain = HeadGain(config.n_head)
        self.rope = nn.RoPE(self.head_dim, traditional=False, base=10000.0)

    def __call__(self, x: mx.array, mask=None, cache=None):
        bsz, seq_len, _ = x.shape
        
        q = self.attn_query(x).reshape(bsz, seq_len, self.n_head, self.head_dim).transpose(0, 2, 1, 3)
        k = self.attn_key(x).reshape(bsz, seq_len, self.n_head, self.head_dim).transpose(0, 2, 1, 3)
        v = self.attn_value(x).reshape(bsz, seq_len, self.n_head, self.head_dim).transpose(0, 2, 1, 3)

        if cache is not None:
            k_cache, v_cache = cache
            q = self.rope(q, offset=k_cache.shape[2])
            k = self.rope(k, offset=k_cache.shape[2])
            k = mx.concatenate([k_cache, k], axis=2)
            v = mx.concatenate([v_cache, v], axis=2)
        else:
            q = self.rope(q)
            k = self.rope(k)
        cache = (k, v)

        q = self.head_gain(q)

        # Scaled dot product attention
        scores = (q @ k.transpose(0, 1, 3, 2)) * (self.head_dim ** -0.5)
        if mask is not None:
            scores = scores + mask
        scores = mx.softmax(scores.astype(mx.float32), axis=-1).astype(scores.dtype)
        
        y = (scores @ v).transpose(0, 2, 1, 3).reshape(bsz, seq_len, -1)
        
        return self.attn_resid(y), cache

class MLP(nn.Module):
    def __init__(self, config: GPTConfig):
        super().__init__()
        n_state = config.n_embd
        n_mlp = int(round(((8 / 3) * n_state) / 128) * 128)

        self.mlp_gate = nn.Linear(n_state, n_mlp, bias=False)
        self.mlp_linear = nn.Linear(n_state, n_mlp, bias=False)
        self.mlp_resid = nn.Linear(n_mlp, n_state, bias=False)

    def __call__(self, x: mx.array):
        gate = self.mlp_gate(x).astype(mx.float32)
        linear = self.mlp_linear(x).astype(mx.float32)
        hidden = nn.silu(gate) * linear
        return self.mlp_resid(hidden.astype(x.dtype))

class Block(nn.Module):
    def __init__(self, config: GPTConfig, layer_idx: int):
        super().__init__()
        self.layer_idx = layer_idx
        self.attn = CausalSelfAttention(config)
        self.attn_gain = ActGain((2 * config.n_layer) ** -0.5)
        self.mlp = MLP(config)
        self.mlp_gain = ActGain((2 * config.n_layer) ** -0.5)
        self.embed_skip = ActGain(0.0)
        
        # Ouroboros Resonance Gate Integration
        self.resonance_gate = OuroborosResonanceGateMLX(config.n_embd, target_layer=15, scale=0.05)

    def __call__(self, e_x: mx.array, x: mx.array, mask=None, cache=None):
        # MLX handles normalization efficiently
        attn_out, new_cache = self.attn(rms_norm(x, eps=1e-5), mask, cache)
        x = x + self.attn_gain(attn_out)
        x = x + self.mlp_gain(self.mlp(rms_norm(x, eps=1e-5)))
        x = x + self.embed_skip(e_x)
        
        # Ouroboros Phase
        x = self.resonance_gate(x, self.layer_idx)
        
        return x, new_cache

class TalkieModelMLX(nn.Module):
    def __init__(self, config: GPTConfig):
        super().__init__()
        self.config = config
        self.embed = nn.Embedding(config.vocab_size, config.n_embd)
        self.blocks = [Block(config, i) for i in range(config.n_layer)]
        self.lm_head = mx.zeros((config.vocab_size, config.n_embd))

        self.lm_head_gain = WeightGain()

    def __call__(self, input_ids: mx.array, cache=None):
        bsz, seq_len = input_ids.shape
        x = self.embed(input_ids).astype(mx.float32)
        x = rms_norm(x, eps=1e-5)
        e_x = x
        
        mask = None
        if seq_len > 1:
            mask = nn.MultiHeadAttention.create_additive_causal_mask(seq_len)
            mask = mask.astype(x.dtype)
        
        new_cache = []
        for i, block in enumerate(self.blocks):
            c = cache[i] if cache is not None else None
            x, c = block(e_x, x, mask=mask, cache=c)
            new_cache.append(c)
            
        x = rms_norm(x, eps=1e-5)
        
        # LM Head execution uses proper lm_head parameter
        logits = x[:, -1, :] @ self.lm_head_gain(self.lm_head).T
        return logits, new_cache

if __name__ == "__main__":
    print("Initializing TalkieModelMLX with Ouroboros integration...")
    config = GPTConfig(n_layer=16) # Smaller for test
    model = TalkieModelMLX(config)
    
    # We can quantize the model instantly in MLX to simulate INT8 weights!
    nn.quantize(model, group_size=64, bits=8)
    
    print("TalkieModelMLX (INT8 Quantized) initialized successfully!")
    
    x = mx.random.randint(0, config.vocab_size, (1, 10))
    
    # mx.compile drastically speeds up inference by fusing the computation graph
    @mx.compile
    def forward_pass(inputs):
        return model(inputs)
        
    out = forward_pass(x)
    mx.eval(out) # Evaluate to force execution
    
    print(f"Forward pass successful! Output shape: {out.shape}")
