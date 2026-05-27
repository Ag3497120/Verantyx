import os
import sys
import time
from deep_translator import GoogleTranslator

def chunk_text(text, max_len=1000):
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_len = 0
    
    for p in paragraphs:
        if current_len + len(p) > max_len and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = []
            current_len = 0
        current_chunk.append(p)
        current_len += len(p) + 2
        
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    return chunks

def translate_markdown(text, target_lang):
    translator = GoogleTranslator(source='ja', target=target_lang)
    chunks = chunk_text(text, 1000)
    translated_chunks = []
    
    for i, chunk in enumerate(chunks):
        print(f"Translating chunk {i+1}/{len(chunks)}...")
        success = False
        for attempt in range(3):
            try:
                res = translator.translate(chunk)
                if res is None:
                    res = chunk
                translated_chunks.append(str(res))
                time.sleep(0.5)
                success = True
                break
            except Exception as e:
                print(f"Error: {e}, retrying...")
                time.sleep(2)
        if not success:
            translated_chunks.append(chunk)
            
    return '\n\n'.join(translated_chunks)

languages = {
    'en': 'README-en.md',
    'es': 'README-es.md',
    'pt': 'README-pt-BR.md',
    'de': 'README-de.md',
    'fr': 'README-fr.md',
    'zh-CN': 'README-zh-CN.md',
    'zh-TW': 'README-zh-TW.md',
    'ko': 'README-ko.md',
    'ar': 'README-ar.md',
    'ru': 'README-ru.md',
    'uk': 'README-uk.md',
    'tr': 'README-tr.md'
}

with open('README.md', 'r', encoding='utf-8') as f:
    original_text = f.read()

for lang_code, filename in languages.items():
    print(f"Translating to {lang_code}...")
    translated_text = translate_markdown(original_text, lang_code)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(translated_text)
    
    print(f"Saved {filename}")

print("All translations done.")
