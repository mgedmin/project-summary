.PHONY: all
all: bin/pip bin/summary        ##: create a local virtualenv with bin/summary

HELP_INDENT = ""
HELP_PREFIX = "make "
HELP_WIDTH = 18
HELP_SEPARATOR = " - "

.PHONY: help
help:                                   ##: describe available make targets
	@grep -E -e '^[a-zA-Z_-]+:.*?##: .*$$' -e '^##:' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":[^#]*##: "}; /^##:/ {printf "\n"} /^[^#]/ {printf "%s\033[36m%-$(HELP_WIDTH)s\033[0m%s%s\n", $(HELP_INDENT), $(HELP_PREFIX) $$1, $(HELP_SEPARATOR), $$2}'

.PHONY: test
test: bin/pytest bin/summary            ##: run tests
	bin/pytest

.PHONY: test
coverage: bin/pytest bin/coverage bin/summary   ##: measure test coverage
	bin/coverage run -m pytest
	bin/coverage report -m

.PHONY: clean
clean:                                  ##: remove build artifacts
	rm -rf .env bin .httpcache.sqlite __pycache__ .pytest_cache/ *.egg-info *.pyc package-lock.json

bin:
	mkdir bin

bin/summary: setup.py | bin/pip
	bin/pip install -e .
	ln -sfr .env/bin/summary bin/

bin/pip: | bin
	python3 -m venv .env
	.env/bin/pip install wheel
	ln -sfr .env/bin/pip bin/

bin/pytest: | bin/pip
	bin/pip install pytest
	ln -sfr .env/bin/pytest bin/

bin/coverage: | bin/pip
	bin/pip install coverage
	ln -sfr .env/bin/coverage bin/

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
