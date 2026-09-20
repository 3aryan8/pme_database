FROM nvidia/cuda:12.2.0-base-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3.11 /usr/bin/python

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Keep the venv OUTSIDE /app so the dev volume mount never shadows or
# clobbers it (issue #14: mixed-OS teams were bricking their host venvs)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./

RUN uv sync

COPY . .

ENTRYPOINT ["uv", "run"]
CMD ["python", "-m", "src.run_pipeline", "--help"]