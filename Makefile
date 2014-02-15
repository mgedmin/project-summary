all: bin/pip bin/summary bin/bower bower_components assets

bin/summary: setup.py
	@test -x bin/pip || make bin/pip
	bin/pip install -e .

bin/pip:
	virtualenv .

bin/bower:
	@mkdir -p bin
	npm install bower
	ln -s ../node_modules/.bin/bower bin/bower

bower_components: bower.json
	@test -x bin/bower || make bin/bower
	bin/bower install
	@touch -c $@

css_dirs = \
    bower_components/bootstrap/dist/css/ \
    bower_components/jquery.tablesorter/css/

css_files = \
    $(foreach dir,$(css_dirs),$(wildcard $(dir)/*.css) $(wildcard $(dir)/*.map))

js_dirs = \
    bower_components/bootstrap/dist/js/ \
    bower_components/jquery/dist/js/ \
    bower_components/jquery.tablesorter/js/

js_files = \
    $(foreach dir,$(js_dirs),$(wildcard $(dir)/*.js) $(wildcard $(dir)/*.map))

font_dirs = \
    bower_components/bootstrap/dist/fonts/

font_files = \
    $(foreach dir,$(font_dirs),$(wildcard $(dir)/*.ttf) $(wildcard $(dir)/*.svg) $(wildcard $(dir)/*.eot) $(wildcard $(dir)/*.woff))

test:
	ls -d $(css_files)

assets:
	@test -d bower_components || make bower_components
	mkdir -p assets/css assets/js assets/fonts
	cp $(css_files) assets/css/
	cp $(js_files) assets/js/
	cp $(font_files) assets/fonts/
