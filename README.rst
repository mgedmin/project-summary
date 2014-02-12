Project Overview
================

I maintain a bunch of Open Source projects.  Most of them on GitHub.

I find it hard to keep track of when a project has accumulated enough important
changes and it's time to make a release.

This is a script to help:

- it runs from cron every night
- re-uses my Jenkins workspaces to get git clones of the projects
  (they're in /var/lib/jenkins/jobs/\*/workspace)
- finds the latest tag in each Git repo (git describe --tags --abbrev=0)
- generates an HTML page with links to GitHub compare view
  (https://github.com/{owner}/{repo}/compare/{tag}...master)

Potential problems, avoided:

- my Jenkins jobs run weekly builds -- not any more, I enabled builds after
  every GH change

How I have it set up:

- cloned this repo into /home/mgedmin/projects on my Jenkins master
- cd /home/mgedmin/projects && make
- created /etc/cron.daily/mg-project-summary, which looks like this::

    #!/bin/sh
    DESTDIR=/var/www/projects.gedmin.as/
    REPORT=$DESTDIR/index.html
    SCRIPT=/home/mgedmin/projects/bin/summary
    ARGS=--html

    if ! test -d $DESTDIR; then
        mkdir -p $DESTDIR
    fi
    $SCRIPT $ARGS > $REPORT.new && mv $REPORT.new $REPORT

- created /var/www/projects.gedmin.as/
- downloaded bootstrap-3.1.0-dist.zip from http://getbootstrap.com
- unzipped it and moved the `css`, `fonts` and `js` subdirectories under
  /var/www/debesis.gedmin.as/projects/
- set up Apache to serve /var/www/projects.gedmin.as at
  http://projects.gedmin.as/

