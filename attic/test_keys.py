import mlx.core as mx
import glob

files = glob.glob("/Users/motonishikoudai/Library/Caches/models/kofdai/talkie-1930-13b-it-mlx-8bit/*.safetensors")
keys = set()
for f in files:
    w = mx.load(f)
    keys.update(w.keys())

quantized_prefixes = set()
for k in keys:
    if k.endswith(".scales"):
        quantized_prefixes.add(k[:-len(".scales")])

print(list(quantized_prefixes)[:10])
