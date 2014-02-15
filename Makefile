all: bin/summary bin/bower bower_components

bin/summary: bin/pip setup.py
	bin/pip install -e .

bin/pip:
	virtualenv .

bin/bower:
	npm install bower
	@mkdir -p bin
	ln -s ../node_modules/.bin/bower bin/bower

bower_components: bin/bower bower.json
	bin/bower install
	@touch -c $@
