install:
	pip install ".[dev]"

test:
	pytest

benchmark:
	veilpierce benchmark

quick:
	veilpierce benchmark synth.n_companies=30000

figures:
	veilpierce figures

docs:
	veilpierce docs

serve:
	veilpierce serve

.PHONY: install test benchmark quick figures docs serve
