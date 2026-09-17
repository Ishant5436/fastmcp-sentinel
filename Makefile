PYTHON ?= ./venv/bin/python
PYTEST ?= $(PYTHON) -m pytest

.PHONY: all csrc test audit demo serve clean

all: csrc test audit

csrc:
	$(MAKE) -C csrc

test: csrc
	$(PYTEST) tests/ -v

audit:
	$(PYTHON) scripts/audit_safety_invariants.py

demo: csrc
	$(PYTHON) scripts/run_demo.py

serve: csrc
	$(PYTHON) -m fastmcp_sentinel.cli serve

clean:
	$(MAKE) -C csrc clean
	rm -rf .pytest_cache tests/__pycache__ src/fastmcp_sentinel/__pycache__ scripts/__pycache__ *.egg-info build dist
