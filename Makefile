.PHONY: check validate lint contracts product

PRODUCT ?= customer_orders

check: validate lint contracts product ## run everything

validate:
	tools/dpf validate

lint:
	tools/dpf lint

contracts:
	python3 tests/contracts/test_contracts.py

product:
	tools/dpf brd validate $(PRODUCT)
	tools/dpf tdd stale
	tools/dpf trace $(PRODUCT)
	tools/dpf compose $(PRODUCT)
