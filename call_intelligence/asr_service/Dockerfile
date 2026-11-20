# Transcription service. Build with the torch wheel for your hardware:
#   docker build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cu130 -t callintel-asr .   (NVIDIA GPU)
#   docker build --build-arg TORCH_INDEX=https://download.pytorch.org/whl/cpu   -t callintel-asr .   (CPU, slow)
# Run with the model folder mounted:
#   docker run --gpus all -p 9000:9000 -v /path/to/eg_callcenter_asr/model:/models/model -e MODEL_PATH=/models/model callintel-asr
FROM python:3.12-slim
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir torch --index-url ${TORCH_INDEX} && pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV MODEL_PATH=/models/model PYTHONUNBUFFERED=1
EXPOSE 9000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "9000"]
