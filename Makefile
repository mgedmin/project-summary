.PHONY: all
all: bin/pip bin/summary

.PHONY: test
test: bin/pytest
	bin/pytest tests.py

clean:
	rm -rf .env bin .httpcache.sqlite __pycache__ .pytest_cache/ *.egg-info *.pyc

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

bin/bower: | bin
	npm install bower
	ln -sf ../node_modules/.bin/bower bin/bower

bower_components: bower.json | bin/bower
	bin/bower install
	@touch -c $@

css_files = \
    bower_components/bootstrap/dist/css/bootstrap.css \
    bower_components/bootstrap/dist/css/bootstrap.css.map \
    bower_components/bootstrap/dist/css/bootstrap.min.css

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

update-assets: bower_components
	rm -rf assets
	mkdir -p assets/css assets/js assets/fonts
	cp $(css_files) assets/css/
	cp $(js_files) assets/js/
	cp $(font_files) assets/fonts/
