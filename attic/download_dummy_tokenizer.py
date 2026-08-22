from transformers import AutoTokenizer
import json

print("Downloading Llama-2 tokenizer as a dummy...")
# Qwen/Qwen1.5-0.5B has 151936, too big.
# mistralai/Mistral-7B-v0.1 has 32000.
tokenizer = AutoTokenizer.from_pretrained("mistralai/Mistral-7B-v0.1")
tokenizer.save_pretrained("/Users/motonishikoudai/Library/Caches/models/kofdai/talkie-1930-13b-it-mlx-8bit/")
print("Saved dummy tokenizer to the model directory.")
