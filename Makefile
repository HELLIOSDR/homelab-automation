.PHONY: install test lint check run

install:
	pip install -r agent/requirements.txt pytest pytest-asyncio

test:
	python3 -m pytest tests/ -v

lint:
	python3 -m py_compile agent/*.py homelab/*.py
	for f in scripts/**/*.sh cascade.sh; do bash -n "$$f"; done

check: lint test

run:
	cd agent && python3 brain.py
