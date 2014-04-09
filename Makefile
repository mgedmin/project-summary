all: bin/pip bin/summary assets

bin/summary: setup.py | bin/pip
	bin/pip install -e .

bin/pip:
	virtualenv .

bin:
	mkdir bin

bin/bower: | bin
	npm install bower
	ln -sf ../node_modules/.bin/bower bin/bower

bower_components: bower.json | bin/bower
	bin/bower install
	@touch -c $@

css_dirs = \
    bower_components/bootstrap/dist/css/ \
    bower_components/jquery.tablesorter/css/

css_files = \
    $(foreach dir,$(css_dirs),$(wildcard $(dir)/*.css) $(wildcard $(dir)/*.map))

js_dirs = \
    bower_components/bootstrap/dist/js/ \
    bower_components/jquery/dist/ \
    bower_components/jquery.tablesorter/js/

js_files = \
    $(foreach dir,$(js_dirs),$(wildcard $(dir)/*.js) $(wildcard $(dir)/*.map))

font_dirs = \
    bower_components/bootstrap/dist/fonts/

font_files = \
    $(foreach dir,$(font_dirs),$(wildcard $(dir)/*.ttf) $(wildcard $(dir)/*.svg) $(wildcard $(dir)/*.eot) $(wildcard $(dir)/*.woff))

assets: | bower_components
	mkdir -p assets/css assets/js assets/fonts
	cp $(css_files) assets/css/
	cp $(js_files) assets/js/
	cp $(font_files) assets/fonts/
