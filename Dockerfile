FROM python:3.10.13-slim

RUN useradd -m -u 1000 user
WORKDIR /home/user/app

# Layer 1: Dependencies (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Layer 2: App code (rebuilt on every push)
COPY --chown=user:user . .

USER user

ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860
EXPOSE 7860

CMD ["python", "app.py"]
