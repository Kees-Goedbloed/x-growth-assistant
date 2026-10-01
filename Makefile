.PHONY: setup test build leak-check

setup:
	bash scripts/setup.sh

build:
	python3 build.py

test:
	python3 -m unittest discover -s tests -v

leak-check:
	bash scripts/check_no_real_data.sh
