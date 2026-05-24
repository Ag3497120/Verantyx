import sys
import os
import torch
import mlx.core as mx
import mlx.nn as nn
from talkie.config import MODELS
from talkie.download import get_model_files
from talkie.tokenizer import build_tokenizer, IT_VOCAB_SIZE, BASE_VOCAB_SIZE
from talkie.model_mlx import TalkieModelMLX, GPTConfig

def load_checkpoint_mlx(checkpoint_path: str, config: GPTConfig, bits: int = 8) -> TalkieModelMLX:
    import gc
    
    # If the file is already a .safetensors file and we downloaded it from our MLX repo
    if checkpoint_path.endswith(".safetensors"):
        print(f"[MLX] Loading native pre-quantized MLX safetensors from {checkpoint_path}...", flush=True)
        model = TalkieModelMLX(config)
        
        def quant_predicate(p, m):
            if not isinstance(m, nn.Linear): return False
            if "embed" in p or "lm_head" in p: return False
            if "talkie-1930-13b-it" in checkpoint_path and "resid" in p: return False
            return True
            
        nn.quantize(model, class_predicate=quant_predicate, group_size=64, bits=bits)
        model.load_weights(checkpoint_path, strict=False)
        return model

    mlx_safetensors_path = checkpoint_path + ".mlx.safetensors"
    
    if os.path.exists(mlx_safetensors_path):
        print(f"[MLX] Loading pre-converted MLX safetensors from {mlx_safetensors_path}...", flush=True)
        model = TalkieModelMLX(config)
        # Quantize structure FIRST so the shapes match the saved quantized weights
        def quant_predicate(p, m):
            if not isinstance(m, nn.Linear): return False
            if "embed" in p or "lm_head" in p: return False
            if "talkie-1930-13b-it" in mlx_safetensors_path and "resid" in p: return False
            return True
            
        nn.quantize(model, class_predicate=quant_predicate, group_size=64, bits=bits)
        model.load_weights(mlx_safetensors_path, strict=False)
        return model

    print("[MLX] Directly Synthesizing MLX Safetensors (Zero Model Allocation)...", flush=True)
    
    ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=True, mmap=True)
    state_dict = ckpt["model_state_dict"] if "model_state_dict" in ckpt else ckpt.get("model", ckpt)
    
    flat_mlx_dict = {}
    keys = list(state_dict.keys())
    for k in keys:
        v = state_dict.pop(k) # Free PyTorch tensor immediately
        new_k = k.replace("_orig_mod.", "")
        arr = mx.array(v.to(torch.float32).numpy()).astype(mx.float16)
        
        # Pad embedding and lm_head weights dynamically for new hidden tokens
        if new_k in ["embed.weight", "lm_head.weight"]:
            from talkie.tokenizer import IT_VOCAB_SIZE
            if arr.shape[0] < IT_VOCAB_SIZE:
                pad_size = IT_VOCAB_SIZE - arr.shape[0]
                pad_arr = mx.zeros((pad_size, arr.shape[1]), dtype=arr.dtype)
                arr = mx.concatenate([arr, pad_arr], axis=0)
        
        # We quantize all linear layer weights except embed, lm_head, and optionally resid
        is_quantizable = ("embed" not in new_k and 
                          "lm_head" not in new_k and 
                          "weight" in new_k and len(arr.shape) == 2)
        if is_quantizable and "talkie-1930-13b-it" in checkpoint_path and "resid" in new_k:
            is_quantizable = False
            
        if is_quantizable:
            q_w, q_s, q_b = mx.quantize(arr, group_size=64, bits=bits)
            mx.eval(q_w, q_s, q_b)
            base_k = new_k.replace(".weight", "")
            flat_mlx_dict[f"{base_k}.weight"] = q_w
            flat_mlx_dict[f"{base_k}.scales"] = q_s
            flat_mlx_dict[f"{base_k}.biases"] = q_b
        else:
            mx.eval(arr)
            flat_mlx_dict[new_k] = arr
            
        del v
        del arr

    del ckpt
    import gc
    gc.collect() # Force garbage collection
    
    print(f"[MLX] Saving ultra-compact MLX weights to {mlx_safetensors_path}...", flush=True)
    mx.save_safetensors(mlx_safetensors_path, flat_mlx_dict)
    del flat_mlx_dict
    
    print(f"[MLX] Conversion complete. Loading natively...", flush=True)
    model = TalkieModelMLX(config)
    def quant_predicate(p, m):
        if not isinstance(m, nn.Linear): return False
        if "embed" in p or "lm_head" in p: return False
        # The local safetensors skipped resid quantization
        if "talkie-1930-13b-it" in checkpoint_path and "resid" in p: return False
        return True
    nn.quantize(model, class_predicate=quant_predicate, group_size=64, bits=bits)
    model.load_weights(mlx_safetensors_path, strict=False)
    
    return model


class GenerationResult:
    def __init__(self, text, token_count, finish_reason):
        self.text = text
        self.token_count = token_count
        self.finish_reason = finish_reason

class TalkieMLX:
    def __init__(self, model_name: str):
        self.spec = MODELS[model_name]
        vocab_size = IT_VOCAB_SIZE if self.spec.style == "it" else BASE_VOCAB_SIZE
        config = GPTConfig(vocab_size=vocab_size)
        
        # If repo is 'local', we skip download and just use the checkpoint_filename
        if self.spec.repo_id == "local":
            ckpt_path = self.spec.checkpoint_filename
            # We assume vocab is in the same directory as the checkpoint
            vocab_path = os.path.join(os.path.dirname(ckpt_path), self.spec.vocab_filename)
            # if vocab doesn't exist there, fallback to downloading talkie-1930-13b-it vocab
            if not os.path.exists(vocab_path):
                _, vocab_path = get_model_files("talkie-1930-13b-it")
            self.tokenizer = build_tokenizer(vocab_path, style=self.spec.style)
        else:
            ckpt_path, vocab_path = get_model_files(model_name)
            self.tokenizer = build_tokenizer(vocab_path, style=self.spec.style)
            
        self.model = load_checkpoint_mlx(str(ckpt_path), config, bits=self.spec.bits)
        
        # Prepare cache for generation
        self.kv_cache = None # Not implemented in naive port, using full sequence for demo
        
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 256, top_p: float = None, top_k: int = None):
        prompt_ids = self.tokenizer.encode(prompt, allowed_special="all")
        x = mx.array([prompt_ids])
        
        def step(inputs, cache, generated_tokens):
            logits, new_cache = self.model(inputs, cache)
            if temperature == 0.0:
                next_token = mx.argmax(logits, axis=-1, keepdims=True)
            else:
                # Simple repetition penalty
                if generated_tokens:
                    # Penalize previously generated tokens
                    unique_tokens = list(set(generated_tokens))
                    indices = mx.array(unique_tokens)
                    penalty = 1.2
                    # We penalize by dividing positive logits and multiplying negative logits
                    penalized_logits = mx.where(logits[0, indices] > 0, 
                                                logits[0, indices] / penalty, 
                                                logits[0, indices] * penalty)
                    logits[0, indices] = penalized_logits
                
                logits = logits / temperature
                next_token = mx.random.categorical(logits)
                if next_token.ndim == 1:
                    next_token = next_token[:, None]
            return next_token, new_cache
            
        tokens = []
        cache = None
        for _ in range(max_tokens):
            next_token, cache = step(x, cache, tokens)
            
            # MLX Memory Leak Fix: Must evaluate cache alongside next_token
            # to prevent the lazy computation graph from growing infinitely.
            eval_items = [next_token]
            if cache is not None:
                for c in cache:
                    if c is not None:
                        eval_items.extend(c)
            mx.eval(*eval_items)
            
            # Clear the MLX Metal allocator pool to prevent 49GB memory leak
            # Clear the MLX cache to prevent memory leak
            if _ % 10 == 0:
                mx.clear_cache()
            
            token_id = next_token.item()
            if token_id == self.tokenizer.encode_single_token("<|endoftext|>") or token_id == self.tokenizer.encode_single_token("<|end|>"):
                break
                
            tokens.append(token_id)
            token_str = self.tokenizer.decode([token_id])
            
            # Stop if we detect it trying to start a new newspaper template
            # Wait, token_str might just be a single letter, but we can check the whole text
            current_text = self.tokenizer.decode(tokens)
            if "[HEADLINE]" in current_text or "[SUBTITLE]" in current_text or "THE NEW YORK TIMES" in current_text[-50:]:
                break
            
            # Use KV cache efficiently: only pass the next token
            x = next_token
            yield token_str
            
        final_text = self.tokenizer.decode(tokens)
        return GenerationResult(text=final_text, token_count=len(tokens), finish_reason="stop")


if __name__ == "__main__":
    print("Initializing MLX Inference Engine...")
    
    # Run the prompt
    prompt = """NEW YORK — A strange, but not altogether
unheard-of, phenomenon occurred yesterday
afternoon. A great ball of fire, about the size
of a barrel, rose from the tracks of the New
York Central Railroad, and flew, at a speed of
500 miles an hour, over the city, passing over
the tallest buildings without touching them. The
fireball, after remaining in sight for"""

    try:
        engine = TalkieMLX("talkie-1930-13b-base")
        engine.generate(prompt)
    except Exception as e:
        print(f"Error during MLX initialization or generation: {e}")
