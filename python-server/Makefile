.PHONY: pull-models setup build-llama-server run-llama-server run-service

pull-models:
	ollama pull llama3.2:3b
	ollama pull all-minilm

setup:
	pyenv install --skip-existing 3.12.12
	poetry install

build-llama-server:
	poetry run pip install llama-stack
	.venv/bin/llama stack build --config configs/build.yaml --image-type venv --image-name .llama-server

run-llama-server:
	.llama-server/bin/llama stack run configs/local-config.yaml

run-service:
	poetry run python app/service.py
