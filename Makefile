all: bin/summary

bin/summary: bin/pip setup.py
	bin/pip install -e .

bin/pip:
	virtualenv .
