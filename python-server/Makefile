PYTHON_VERSION = 3.12

.PHONY: pull-models setup build-llama-server run-llama-server run-service

pull-models:
	ollama pull llama3.2:3b
	ollama pull all-minilm

setup:
	poetry env use $$(pyenv which python$(PYTHON_VERSION))
	poetry install

build-llama-server:
	.venv/bin/pip install llama-stack
	.venv/bin/llama stack build --config configs/build.yaml --image-type venv --image-name .llama-server

run-llama-server:
	.llama-server/bin/llama stack run configs/local-config.yaml

run-service:
	.venv/bin/python app/service.py
