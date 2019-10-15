Project Overview
================

I maintain a bunch of Open Source projects.  Most of them in Python.
Most of them on GitHub.

I find it hard to keep track of when a project has accumulated enough important
changes and it's time to make a release.

This is a script to help:

- it runs as a Jenkins job every hour
- re-uses my Jenkins workspaces to look at git clones of the projects
  (they're in /var/lib/jenkins/jobs/\*/workspace)
- finds the latest tag in each Git repo and counts commit since them
- collects some other data from the public GitHub API (such as the number of
  open issues) and other sources (such as Python version support classifiers in
  setup.py).
- generates an HTML page with all this information

You can see the result at https://projects.gedmin.as/


Setup
~~~~~

- set up a Jenkins job to build this hourly
  (make && bin/summary --html -o index.html)
- create /var/www/projects.gedmin.as/
- symlink /var/lib/jenkins/jobs/project-summary/assets and index.html
  into /var/www/projects.gedmin.as/
- set up Apache to serve /var/www/projects.gedmin.as at
  https://projects.gedmin.as/


Alternative setup (no Jenkins)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- check out this repository somewhere (e.g. /opt/project-summary)
- check out all your projects somewhere else (e.g. under /srv/project-summary/)
- create a cron script to run::

    cd /opt/project-summary && make -s && bin/summary --pull --html -o index.html

- create /var/www/projects.gedmin.as/
- symlink /opt/project-summary/assets and index.html
  into /var/www/projects.gedmin.as/
- set up Apache to serve /var/www/projects.gedmin.as at
  https://projects.gedmin.as/


Can anyone else use this?
~~~~~~~~~~~~~~~~~~~~~~~~~

Probably!  Don't hesitate to file bugs (or pull requests) asking for more
configurability, or for a release to PyPI.

Check out project-summary.cfg for the current configuration options.


Note on HTTP request caching
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HTTP requests are cached for 30 minutes by default, in an SQLite database
called ``.httpcache.sqlite``.

This is because I run the script rather often while I'm developing it,
and without caching the script takes a long time to run.  Also, I don't want to
run into GitHub's public API rate limits (60 requests per hour).

You can change the cache duration by specifying, e.g. ``--cache-duration 5m``
(valid units are seconds, minutes and hours and can be abbreviated to
sec/min/hour or s/m/h).
