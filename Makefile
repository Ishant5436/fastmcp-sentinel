PYTHON ?= $(if $(wildcard ./venv/bin/python),./venv/bin/python,python3)
PYTEST ?= $(PYTHON) -m pytest

.PHONY: all dev csrc cmake-build native-test sanitize lint format typecheck test cov audit demo serve check build clean

all: csrc lint typecheck test audit

dev:
	$(PYTHON) -m pip install -e ".[dev]"
	$(MAKE) csrc

csrc:
	$(MAKE) -C csrc

cmake-build:
	cmake -S . -B build/dev && cmake --build build/dev

native-test: cmake-build
	ctest --test-dir build/dev --output-on-failure

sanitize:
	cmake -S . -B build/asan -DCMAKE_BUILD_TYPE=Debug -DSENTINEL_SANITIZE=ON && cmake --build build/asan
	ctest --test-dir build/asan --output-on-failure

lint:
	$(PYTHON) -m ruff check src tests scripts
	$(PYTHON) -m ruff format --check src tests scripts

format:
	$(PYTHON) -m ruff check --fix src tests scripts
	$(PYTHON) -m ruff format src tests scripts

typecheck:
	$(PYTHON) -m mypy

test: csrc
	$(PYTEST)

cov: csrc
	$(PYTEST) --cov --cov-report=term-missing

audit:
	$(PYTHON) -m fastmcp_sentinel.cli audit --csrc-dir csrc

demo: csrc
	$(PYTHON) -m fastmcp_sentinel.cli demo

check: csrc
	$(PYTHON) -m fastmcp_sentinel.cli check

serve: csrc
	$(PYTHON) -m fastmcp_sentinel.cli serve

build:
	$(PYTHON) -m build --outdir dist

clean:
	$(MAKE) -C csrc clean
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +

# --- Smart contracts (Foundry) ---------------------------------------------------
.PHONY: contracts contracts-test contracts-fmt app

contracts:
	cd contracts && forge build

contracts-test:
	cd contracts && forge test -vvv

contracts-fmt:
	cd contracts && forge fmt

app:
	@echo "Serving app/ at http://127.0.0.1:8000/?vault=<address>"
	$(PYTHON) -m http.server 8000 --directory app
