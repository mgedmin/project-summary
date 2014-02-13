#!/usr/bin/python
"""
Generate a summary for all my projects.
"""

import glob
import os
import subprocess
import argparse
from cgi import escape

try:
    import arrow
except ImportError:
    arrow = None


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.5'


#
# Configuration
#

REPOS = '/var/lib/jenkins/jobs/*/workspace'


#
# Utilities
#

def pipe(*cmd, **kwargs):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, **kwargs)
    return p.communicate()[0]


#
# Data extraction
#

def get_repos():
    return sorted(dirname for dirname in glob.glob(REPOS)
                  if os.path.isdir(os.path.join(dirname, '.git')))


def get_repo_url(repo_path):
    return pipe("git", "remote", "-v", cwd=repo_path).splitlines()[0].split()[1]


def normalize_github_url(url):
    if not url.startswith('https://github.com/'):
        return url
    if url.endswith('.git'):
        url = url[:-len('.git')]
    return url


def get_project_owner(url):
    return url.rpartition('/')[0].rpartition('/')[-1]


def get_project_name(url):
    return url.rpartition('/')[-1]


def get_last_tag(repo_path):
    return pipe("git", "describe", "--tags", "--abbrev=0",
                cwd=repo_path).strip()


def get_date_of_tag(repo_path, tag):
    return pipe("git", "log", "-1", "--format=%ai", tag, cwd=repo_path).strip()


def get_pending_commits(repo_path, last_tag):
    return pipe("git", "log", "--oneline", "{}..origin/master".format(last_tag),
                cwd=repo_path).splitlines()


class Project(object):

    def __init__(self, working_tree, url, last_tag, last_tag_date,
                 pending_commits):
        self.working_tree = working_tree
        self.url = url
        self.last_tag = last_tag
        self.last_tag_date = last_tag_date
        self.pending_commits = pending_commits

    @classmethod
    def from_working_tree(cls, working_tree):
        url = normalize_github_url(get_repo_url(working_tree))
        last_tag = get_last_tag(working_tree)
        last_tag_date = get_date_of_tag(working_tree, last_tag)
        pending_commits = get_pending_commits(working_tree, last_tag)
        return cls(working_tree, url, last_tag, last_tag_date, pending_commits)

    @property
    def owner(self):
        return get_project_owner(self.url)

    @property
    def name(self):
        return get_project_name(self.url)

    @property
    def compare_url(self):
        return '{base}/compare/{tag}...master'.format(base=self.url,
                                                      tag=self.last_tag)

    @property
    def travis_image_url(self):
        # Travis has 19px-high PNG images
        template = 'https://travis-ci.org/{owner}/{name}.png?branch=master'
        # Shields.io give me 18px-high SVG and PNG images that look better,
        # but are slower or even fail to load (rate limiting?)
        ## template = '//img.shields.io/travis/{owner}/{name}/master.svg'
        return template.format(name=self.name, owner=self.owner)

    @property
    def travis_url(self):
        return 'https://travis-ci.org/{owner}/{name}'.format(
                    name=self.name, owner=self.owner)


def get_projects():
    for path in get_repos():
        yield Project.from_working_tree(path)


#
# Report generation
#

template = '''\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <title>{title}</title>

    <link rel="stylesheet" href="css/bootstrap.min.css">
    <link rel="stylesheet" href="css/bootstrap-theme.min.css">

    <style type="text/css">
      td > a > img {{ position: relative; top: -2px; }}
    </style>

    <!-- HTML5 shim and Respond.js IE8 support of HTML5 elements and media queries -->
    <!--[if lt IE 9]>
      <script src="https://oss.maxcdn.com/libs/html5shiv/3.7.0/html5shiv.js"></script>
      <script src="https://oss.maxcdn.com/libs/respond.js/1.4.2/respond.min.js"></script>
    <![endif]-->
  </head>
  <body role="document">
    <div class="container">
      <div class="page-header">
        <h1>{title}</h1>
      </div>
      <table class="table table-hover">
        <thead>
          <tr>
            <th>Name</th>
            <th>Last release</th>
            <th>Date</th>
            <th>Pending changes</th>
            <th>Build status</th>
          </tr>
        </thead>
        <tbody>
{rows}
        </tbody>
      </table>
    </div>
  </body>
</html>
'''


row_template = '''\
        <tr>
          <td>{name}</td>
          <td>{tag}</td>
          <td title="{full_date}">{date}</td>
          <td>{changes}</td>
          <td>{build_status}</td>
        </tr>
'''


def nice_date(date_string):
    if not arrow:
        return date_string
    return arrow.get(date_string).humanize()


def link(url, text):
    return '<a href="{}">{}</a>'.format(escape(url, True), text)


def image(url, alt):
    return '<img src="{}" alt="{}">'.format(escape(url, True), alt)


def pluralize(number, noun):
    if number == 1:
        noun = noun[:-1]  # poor Englishman's i18n
    return '{} {}'.format(number, noun)


def main():
    parser = argparse.ArgumentParser(
            description="Summarize release status of projects in %s" % REPOS)
    parser.add_argument('--version', action='version',
                        version="%(prog)s version " + __version__)
    parser.add_argument('-v', '--verbose', action='count',
                        help='be more verbose (can be repeated)')
    parser.add_argument('--html', action='store_true',
                        help='produce HTML output')
    args = parser.parse_args()
    if args.html:
        print_html_report(get_projects())
    else:
        print_report(get_projects(), args.verbose)


def print_report(projects, verbose):
    for project in projects:
        print("{name:20} {commits:4} commits since {release:6} ({date})".format(
            name=project.name, commits=len(project.pending_commits),
            release=project.last_tag, date=nice_date(project.last_tag_date)))
        if verbose:
            print("  {}".format(project.compare_url))
            if verbose > 1:
                print("  {}".format(project.working_tree))
            print("")


def print_html_report(projects):
    print(template.format(
            title='Projects',
            rows='\n'.join(
                row_template.format(
                    name=link(project.url, escape(project.name)),
                    tag=escape(project.last_tag),
                    date=escape(nice_date(project.last_tag_date)),
                    full_date=escape(project.last_tag_date),
                    build_status=link(project.travis_url,
                        image(project.travis_image_url, 'Build Status')),
                    changes=link(project.compare_url,
                        escape(pluralize(len(project.pending_commits),
                                         'commits'))),
                ) for project in projects),
        ))


if __name__ == '__main__':
    main()
