.PHONY: install test lint check run healthcheck

install:
	pip install -r agent/requirements.txt pytest pytest-asyncio psutil pydantic fastapi aiohttp python-dotenv

test:
	python3 -m pytest tests/ -v

lint:
	@for f in agent/*.py agent/sensors/*.py homelab/*.py; do \
		python3 -m py_compile "$$f" && echo "OK: $$f"; \
	done
	@for f in scripts/adb/*.sh scripts/root/*.sh scripts/termux/*.sh cascade.sh; do \
		bash -n "$$f" && echo "OK: $$f"; \
	done

check: lint test

healthcheck:
	cd agent && python3 healthcheck.py

run:
	cd agent && python3 brain.py

install-hooks:
	cp .git-hooks/pre-push .git/hooks/pre-push
	chmod +x .git/hooks/pre-push
	echo "Hook pre-push zainstalowany"
