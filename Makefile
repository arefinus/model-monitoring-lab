PYTHON ?= python
PKG = model_monitoring_lab

.PHONY: setup smoke demo test evaluate figures fixture clean

setup:
	pip install -e . && pip install pytest

smoke:
	$(PYTHON) -m $(PKG) smoke

demo:
	$(PYTHON) -m $(PKG) demo

test:
	$(PYTHON) -m pytest -q

evaluate:
	$(PYTHON) -m $(PKG) alerts --report examples/output/monitoring_report.json

figures:
	$(PYTHON) -m $(PKG) figures

fixture:
	$(PYTHON) tools/make_fixture.py

clean:
	rm -rf .pytest_cache src/$(PKG)/__pycache__ tests/__pycache__
