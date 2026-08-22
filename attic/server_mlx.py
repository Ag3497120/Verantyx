import mlx.core as mx
import mlx.nn as nn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import glob
import os
import asyncio

from model_mlx import TalkieModelMLX, GPTConfig
from transformers import AutoTokenizer
from outlines.models.mlxlm import MLXLM
from outlines.generator import get_json_schema_logits_processor

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

print("Loading TalkieModelMLX from 4-bit safetensors...")
# Base config and tokenizer from the 8-bit dir (since they share the same vocab and structure)
model_path = "/Users/motonishikoudai/Library/Caches/models/kofdai/talkie-1930-13b-it-mlx-8bit"
# Direct 4-bit safetensors file
safetensors_file = "/Users/motonishikoudai/.cache/huggingface/hub/models--talkie-lm--talkie-1930-13b-it/snapshots/8033675be6360ae0127fa75f941c12d52064f1dc/rl-refined.pt.mlx-4bit.safetensors"


tokenizer = AutoTokenizer.from_pretrained(model_path)

config_path = f"{model_path}/config.json"
with open(config_path) as f:
    config_dict = json.load(f)

config = GPTConfig(
    vocab_size=config_dict.get("vocab_size", 65536),
    n_layer=config_dict.get("num_hidden_layers", 40),
    n_head=config_dict.get("num_attention_heads", 40),
    n_embd=config_dict.get("hidden_size", 5120),
)

# Custom override for number of KV heads if it exists
if "num_key_value_heads" in config_dict:
    config.n_kv_head = config_dict["num_key_value_heads"]
else:
    config.n_kv_head = config.n_head

model = TalkieModelMLX(config)

# Cast all float32 initialized parameters to float16 to prevent memory explosion!
from mlx.utils import tree_map
def cast_to_fp16(x):
    if isinstance(x, mx.array) and x.dtype == mx.float32:
        return x.astype(mx.float16)
    return x
model.update(tree_map(cast_to_fp16, model.parameters()))

if "quantization_config" in config_dict:
    q_config = config_dict["quantization_config"]
    
    from mlx.utils import tree_map_with_path
    
    def make_quantized(path, m):
        if not isinstance(m, nn.Linear): return m
        quant_names = ["attn_query", "attn_key", "attn_value", "mlp_gate", "mlp_linear"]
        if any(n in path for n in quant_names):
            return nn.QuantizedLinear(m.weight.shape[1], m.weight.shape[0], bias="bias" in m, group_size=q_config.get("group_size", 64), bits=4)
        return m

    leaves = model.leaf_modules()
    leaves = tree_map_with_path(make_quantized, leaves, is_leaf=nn.Module.is_module)
    model.update_modules(leaves)


from mlx.utils import tree_unflatten

print(f"Loading weights from {safetensors_file}...")
weights = mx.load(safetensors_file)

weights = tree_unflatten(list(weights.items()))
model.update(weights)
mx.eval(model.parameters())
print("Model loaded successfully!")

def generate_step(prompt_ids, temp=0.12, logits_processor=None):
    cache = None
    y = prompt_ids
    all_tokens = prompt_ids
    
    while True:
        logits, cache = model(y, cache=cache)
        
        if logits_processor is not None:
            # outlines expects mlx arrays and returns processed logits
            logits = logits_processor(all_tokens, logits)
            
        if temp == 0:
            next_token = mx.argmax(logits, axis=-1)
        else:
            logits = logits / temp
            next_token = mx.random.categorical(logits)
            
        y = next_token.reshape(1, 1)
        all_tokens = mx.concatenate([all_tokens, y], axis=1)
        mx.eval(y)
        token_id = next_token.item()
        yield token_id

async def stream_generator(prompt: str, max_tokens: int = 1024, response_format: dict = None):
    prompt_ids = tokenizer.encode(prompt, return_tensors="np")
    prompt_ids = mx.array(prompt_ids)
    
    logits_processor = None
    if response_format is not None and response_format.get("type") == "json_schema":
        schema_dict = response_format.get("json_schema", {}).get("schema", {})
        if schema_dict:
            outlines_model = MLXLM(model, tokenizer)
            logits_processor = get_json_schema_logits_processor("outlines_core", outlines_model, json.dumps(schema_dict))
    
    gen = generate_step(prompt_ids, logits_processor=logits_processor)
    
    for i, token_id in enumerate(gen):
        if i >= max_tokens or token_id == tokenizer.eos_token_id:
            break
            
        text = tokenizer.decode([token_id])
        yield text
        await asyncio.sleep(0) # Yield control

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    
    # LLaMA 2 Instruct format
    prompt = ""
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            prompt += f"[INST] {content} [/INST]\n"
        elif role == "assistant":
            prompt += f"{content}\n"
    
    max_tokens = data.get("max_tokens", 1024)
    response_format = data.get("response_format")
    
    async def event_stream():
        async for chunk in stream_generator(prompt, max_tokens, response_format):
            response = {
                "choices": [
                    {
                        "delta": {"content": chunk}
                    }
                ]
            }
            yield f"data: {json.dumps(response)}\n\n"
        yield "data: [DONE]\n\n"
        
    return StreamingResponse(event_stream(), media_type="text/event-stream")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
