import json
import struct
import glob
import os

st_file = glob.glob("/Users/motonishikoudai/Library/Caches/models/kofdai/talkie-1930-13b-it-mlx-8bit/*.safetensors")[0]
with open(st_file, 'rb') as f:
    header_size = struct.unpack('<Q', f.read(8))[0]
    header = f.read(header_size)
    metadata = json.loads(header)
    print("embed.weight:", metadata.get("embed.weight", "NOT FOUND"))
    print("lm_head:", metadata.get("lm_head", "NOT FOUND"))
    print("lm_head.weight:", metadata.get("lm_head.weight", "NOT FOUND"))
    print("lm_head_gain.w_g:", metadata.get("lm_head_gain.w_g", "NOT FOUND"))
