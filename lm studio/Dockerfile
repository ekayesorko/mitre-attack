FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    wget \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://lmstudio.ai/api/get/windows/latest -O lm-studio.zip && \
    unzip lm-studio.zip && \
    rm lm-studio.zip

EXPOSE 1234 8000

ENV PATH="/app:${PATH}"

CMD ["./LM\ Studio"]