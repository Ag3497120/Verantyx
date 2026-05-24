FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all files
COPY . .

# Download DB from Model Repo (to save Space storage)
# This runs during build time
RUN python tools/download_db_for_space.py

# Environment variables
ENV PYTHONUNBUFFERED=1

# Hugging Face Spaces expects port 7860
EXPOSE 7860

# Run the server
CMD ["python", "phase17_ui_server.py", \
     "--kb", "avh_math/db/foundation_kb.jsonl", \
     "--offsets", "avh_math/db/kb_offsets.json", \
     "--index", "avh_math/db/kb_index.json", \
     "--graph", "avh_math/db/boundary_graph.json", \
     "--meta", "avh_math/db/kb_meta.json", \
     "--static-dir", "phase17_static", \
     "--port", "7860"]