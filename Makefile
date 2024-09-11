pypackage = project_summary

.PHONY: all
all: bin/pip bin/summary        ##: create a local virtualenv with bin/summary

HELP_INDENT = ""
HELP_PREFIX = "make "
HELP_WIDTH = 24
HELP_SEPARATOR = " - "

.PHONY: help
help:                                   ##: describe available make targets
	@grep -E -e '^[a-zA-Z_-]+:.*?##: .*$$' -e '^##:' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":[^#]*##: "}; /^##:/ {printf "\n"} /^[^#]/ {printf "%s\033[36m%-$(HELP_WIDTH)s\033[0m%s%s\n", $(HELP_INDENT), $(HELP_PREFIX) $$1, $(HELP_SEPARATOR), $$2}'

.PHONY: test
test:                                   ##: run tests
	tox -p auto

.PHONY: coverage
coverage:                               ##: measure test coverage
	tox -e coverage

.PHONY: clean
clean:                                  ##: remove build artifacts
	rm -rf .venv bin .httpcache.sqlite __pycache__ .pytest_cache/ *.egg-info *.pyc package-lock.json

.PHONY: update-all-packages
update-all-packages: bin/pip            ##: upgrade all packages to latest versions
	bin/pip install -U pip setuptools wheel
	bin/pip install -U --upgrade-strategy=eager -e .
	make update-requirements

.PHONY: update-requirements
update-requirements: bin/pip            ##: regenerate requirements.txt from currently installed versions
	PYTHONPATH= bin/pip freeze | grep -v '^-e .*$(pypackage)$$' > requirements.txt

.PHONY: tags
tags:   bin/summary
	ctags -R summary.py .venv/lib/

bin:
	mkdir bin

bin/summary: setup.py requirements.txt | bin/pip
	bin/pip install -e . -c requirements.txt
	ln -sfr .venv/bin/summary bin/
	@touch -c $@

bin/pip: | bin
	virtualenv -p python3 .venv
	.venv/bin/pip install -U pip
	ln -sfr .venv/bin/pip bin/

bin/bower: | bin
	npm install bower
	ln -sf ../node_modules/.bin/bower bin/bower

bower_components: bower.json | bin/bower
	bin/bower install
	@touch -c $@

css_files = \
    bower_components/bootstrap/dist/css/bootstrap.css \
    bower_components/bootstrap/dist/css/bootstrap.css.map \
    bower_components/bootstrap/dist/css/bootstrap.min.css \
    bower_components/bootstrap/dist/css/bootstrap.min.css.map

js_files = \
    bower_components/bootstrap/dist/js/bootstrap.js \
    bower_components/bootstrap/dist/js/bootstrap.min.js \
    bower_components/jquery/dist/jquery.js \
    bower_components/jquery/dist/jquery.min.js \
    bower_components/jquery/dist/jquery.min.map \
    bower_components/jquery.tablesorter/dist/js/jquery.tablesorter.js \
    bower_components/jquery.tablesorter/dist/js/jquery.tablesorter.min.js \
    bower_components/jquery.tablesorter/dist/js/jquery.tablesorter.widgets.js \
    bower_components/jquery.tablesorter/dist/js/jquery.tablesorter.widgets.min.js

font_files = \
    bower_components/bootstrap/dist/fonts/*.ttf \
    bower_components/bootstrap/dist/fonts/*.svg \
    bower_components/bootstrap/dist/fonts/*.eot \
    bower_components/bootstrap/dist/fonts/*.woff*

.PHONY: update-assets
update-assets: bower_components         ##: update assets files from bower.json
	rm -rf assets
	mkdir -p assets/css assets/js assets/fonts
	cp $(css_files) assets/css/
	cp $(js_files) assets/js/
	cp $(font_files) assets/fonts/
