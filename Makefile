.PHONY: build shell test verify-gpu clean gpu

COMPOSE := docker compose -f docker/docker-compose.yml
COMPOSE_GPU := docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml

build:
	$(COMPOSE) build

shell:
	$(COMPOSE) run --rm foundation bash

# Verifies GPU passthrough (nvidia-smi must work inside the container)
verify-gpu:
	$(COMPOSE_GPU) run --rm foundation python src/verify_gpu.py

test:
	$(COMPOSE) run --rm foundation pytest tests/ -v

# Runs a command inside the container WITH GPU access (Phase 5+ only)
# Usage: make gpu CMD="python -m src.detection.pose_splits"
gpu:
	$(COMPOSE_GPU) run --rm foundation $(CMD)

clean:
	find data/interim data/metadata data/processed -type f ! -name '.gitkeep' -delete
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
