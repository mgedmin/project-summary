Project Overview
================

I maintain a bunch of Open Source projects.  Most of them on GitHub.

I find it hard to keep track of when a project has accumulated enough important
changes and it's time to make a release.

This is a script to help:

- it runs as a Jenkins job every hour
- re-uses my Jenkins workspaces to get git clones of the projects
  (they're in /var/lib/jenkins/jobs/\*/workspace)
- finds the latest tag in each Git repo (git describe --tags --abbrev=0)
- generates an HTML page with links to GitHub compare view
  (https://github.com/{owner}/{repo}/compare/{tag}...master)

Potential problems, avoided:

- my Jenkins jobs run weekly builds -- not any more, I enabled builds after
  every GH change

Setup:

- set up a Jenkins job to build this hourly
  (make && bin/summary --html > index.html)
- create /var/www/projects.gedmin.as/
- symlink /var/lib/jenkins/jobs/project-summary/assets and index.html
  into /var/www/projects.gedmin.as/
- set up Apache to serve /var/www/projects.gedmin.as at
  http://projects.gedmin.as/

