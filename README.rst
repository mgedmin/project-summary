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
  http://projects.gedmin.as/


Can anyone else use this?
~~~~~~~~~~~~~~~~~~~~~~~~~

Probably!  Don't hesitate to file bugs (or pull requests) asking for more
configurability.

Currently all the configuration is hardcoded near the top of ``summary.py``
and in ``repos.txt``.  It should be moved to a config file.
