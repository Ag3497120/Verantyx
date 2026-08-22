import json
import struct
import glob
import os

st_file = glob.glob("/Users/motonishikoudai/Library/Caches/models/kofdai/talkie-1930-13b-it-mlx-8bit/*.safetensors")[0]
with open(st_file, 'rb') as f:
    header_size = struct.unpack('<Q', f.read(8))[0]
    header = f.read(header_size)
    metadata = json.loads(header)
    keys = list(metadata.keys())
    keys.sort()
    for k in keys:
        print(k)
