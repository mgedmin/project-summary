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
__version__ = '0.7.0'

here = os.path.dirname(__file__)


#
# Configuration
#

REPOS = 'repos.txt'
IGNORE = []


#
# Utilities
#

def pipe(*cmd, **kwargs):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, **kwargs)
    return p.communicate()[0].decode('UTF-8', 'replace')


class reify(object):
    def __init__(self, fn):
        self.fn = fn

    def __get__(self, obj, cls=None):
        value = self.fn(obj)
        obj.__dict__[self.fn.__name__] = value
        return value


#
# Data extraction
#

def get_repos():
    with open(os.path.join(here, REPOS)) as f:
        paths = (line.strip() for line in f
                 if line.strip() and not line.lstrip().startswith('#'))
        return sorted(
            dirname
            for path in paths
            for dirname in glob.glob(os.path.expanduser(path))
            if os.path.isdir(os.path.join(dirname, '.git')))


def get_repo_url(repo_path):
    try:
        return pipe("git", "ls-remote", "--get-url", "origin", cwd=repo_path).strip()
    except IndexError:
        return None


def normalize_github_url(url):
    if not url:
        return url
    if url.startswith('git://github.com/'):
        url = 'https://github.com/' + url[len('git://github.com/'):]
    elif url.startswith('git@github.com:'):
        url = 'https://github.com/' + url[len('git@github.com:'):]
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
                cwd=repo_path, stderr=subprocess.PIPE).strip()


def get_date_of_tag(repo_path, tag):
    return pipe("git", "log", "-1", "--format=%ai", tag, cwd=repo_path).strip()


def get_pending_commits(repo_path, last_tag):
    return pipe("git", "log", "--oneline", "{}..origin/master".format(last_tag),
                cwd=repo_path).splitlines()


class Project(object):

    def __init__(self, working_tree):
        self.working_tree = working_tree

    @reify
    def url(self):
        return normalize_github_url(get_repo_url(self.working_tree))

    @reify
    def is_on_github(self):
        return self.url.startswith('https://github.com/')

    @reify
    def uses_travis(self):
        if not self.is_on_github:
            return False
        return os.path.exists(os.path.join(self.working_tree, '.travis.yml'))

    @property
    def uses_jenkins(self):
        return self.owner in ('mgedmin', 'gtimelog')

    @reify
    def last_tag(self):
        return get_last_tag(self.working_tree)

    @reify
    def last_tag_date(self):
        return get_date_of_tag(self.working_tree, self.last_tag)

    @reify
    def pending_commits(self):
        return get_pending_commits(self.working_tree, self.last_tag)

    @property
    def owner(self):
        if self.is_on_github:
            return get_project_owner(self.url)
        else:
            return None

    @property
    def name(self):
        if self.url:
            return get_project_name(self.url)
        else:
            return os.path.basename(self.working_tree)

    @property
    def compare_url(self):
        if not self.is_on_github:
            return None
        return '{base}/compare/{tag}...master'.format(base=self.url,
                                                      tag=self.last_tag)

    @property
    def travis_image_url(self):
        if not self.uses_travis:
            return None
        # Travis has 19px-high PNG images and 18px-high SVG images
        template = 'https://api.travis-ci.org/{owner}/{name}.svg?branch=master'
        # Shields.io give me 18px-high SVG and PNG images that look better,
        # but are slower or even fail to load (rate limiting?)
        ## template = '//img.shields.io/travis/{owner}/{name}/master.svg'
        return template.format(name=self.name, owner=self.owner)

    @property
    def travis_url(self):
        if not self.uses_travis:
            return None
        return 'https://travis-ci.org/{owner}/{name}'.format(name=self.name,
                                                             owner=self.owner)

    @property
    def coveralls_image_url(self):
        if not self.uses_travis:
            return None
        # 18px-high PNG
        template = 'https://coveralls.io/repos/{owner}/{name}/badge.png?branch=master'
        # SVG from shields.io (slow/nonfunctional)
        ## template = 'https://img.shields.io/coveralls/{owner}/{name}.svg'
        return template.format(name=self.name, owner=self.owner)

    @property
    def coveralls_url(self):
        if not self.uses_travis:
            return None
        return 'https://coveralls.io/r/{owner}/{name}'.format(name=self.name,
                                                              owner=self.owner)

    @property
    def jenkins_image_url(self):
        if not self.uses_jenkins:
            return None
        return 'https://jenkins.gedmin.as/job/{name}/badge/icon'.format(name=self.name)

    @property
    def jenkins_url(self):
        if not self.uses_jenkins:
            return None
        return 'https://jenkins.gedmin.as/job/{name}/'.format(name=self.name)

    @property
    def jenkins_image_url_windows(self):
        if not self.uses_jenkins:
            return None
        job = self.name + '-on-windows'
        return 'https://jenkins.gedmin.as/job/{name}/badge/icon'.format(name=job)

    @property
    def jenkins_url_windows(self):
        if not self.uses_jenkins:
            return None
        job = self.name + '-on-windows'
        return 'https://jenkins.gedmin.as/job/{name}/'.format(name=job)


def get_projects():
    for path in get_repos():
        p = Project(path)
        if p.name not in IGNORE and p.last_tag:
            yield p


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

    <link rel="stylesheet" href="assets/css/bootstrap.min.css">

    <style type="text/css">
      td > a > img {{ position: relative; top: -1px; }}
      .tablesorter-icon {{ color: #ddd; }}
      .tablesorter-header {{ cursor: default; }}
      #release-status th:nth-child(3), #release-status td:nth-child(3) {{ text-align: right; }}
      #release-status th:nth-child(4), #release-status td:nth-child(4) {{ text-align: right; }}
      #release-status th:nth-child(5), #release-status td:nth-child(5) {{ text-align: right; }}
      footer {{ padding-top: 16px; padding-bottom: 20px; text-align: center; color: #999; }}
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
        <div class="btn-group pull-right" role="menu">
          <a class="btn btn-primary" data-toggle="tab" href="#release-status">Release status</a>
          <a class="btn btn-default" data-toggle="tab" href="#maintenance">Maintenance</a>
        </div>
        <h1>{title}</h1>
      </div>
      <div class="tab-content">
        <div class="tab-pane active" id="release-status">
          {release_status_table}
        </div>
        <div class="tab-pane" id="maintenance">
          {maintenance_table}
        </div>
      </div>
    </div>
    <footer>
      <div class="container">
        An incomplete list of FOSS projects maintained by <a href="https://github.com/mgedmin">@mgedmin</a>.
        Updated hourly by a <a href="https://jenkins.gedmin.as/job/project-summary/">Jenkins job</a>.
      </div>
    </footer>
{javascript}
  </body>
</html>
'''


release_status_table_template = '''\
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
'''


release_status_row_template = '''\
          <tr>
            <td>{name}</td>
            <td>{tag}</td>
            <td title="{full_date}">{date}</td>
            <td>{changes}</td>
            <td>{build_status}</td>
          </tr>
'''


maintenance_table_template = '''\
      <table class="table table-hover">
        <thead>
          <tr>
            <th>Name</th>
            <th>Travis CI</th>
            <th>Jenkins (Linux)</th>
            <th>Jenkins (Windows)</th>
            <th>Coveralls</th>
          </tr>
        </thead>
        <tbody>
{rows}
        </tbody>
      </table>
'''


maintenance_table_row_template = '''\
          <tr>
            <td>{name}</td>
            <td>{build_status}</td>
            <td>{jenkins_status}</td>
            <td>{jenkins_windows_status}</td>
            <td>{coveralls_status}</td>
          </tr>
'''


javascript = '''\
    <script src="assets/js/jquery.min.js"></script>
    <script src="assets/js/jquery.tablesorter.min.js"></script>
    <script src="assets/js/jquery.tablesorter.widgets.min.js"></script>
    <script src="assets/js/bootstrap.min.js"></script>
    <script>
      $(function() {
        $.extend($.tablesorter.themes.bootstrap, {
            table      : '',
            caption    : '',
            header     : '',
            footerRow  : '',
            footerCells: '',
            icons      : '',
            sortNone   : '',
            sortAsc    : 'glyphicon glyphicon-sort-by-attributes',
            sortDesc   : 'glyphicon glyphicon-sort-by-attributes-alt',
            active     : '',
            hover      : 'active',
            filterRow  : '',
            even       : '',
            odd        : ''
          });
        $("#release-status table").tablesorter({
          theme: "bootstrap",
          widgets: ['uitheme'],
          widthFixed: true,
          textExtraction: {
            2: function(node, table, cellIndex) { return $(node).attr('title'); }
          }
        });
        $("#maintenance table").tablesorter({
          theme: "bootstrap",
          widgets: ['uitheme'],
          widthFixed: true,
        });
        var dont_recurse = false;
        $('a[data-toggle="tab"]').on('shown.bs.tab', function(e) {
          $(e.target).siblings('.btn-primary').removeClass('btn-primary').addClass('btn-default');
          $(e.target).removeClass('btn-default').addClass('btn-primary');
          if (!dont_recurse) {
            dont_recurse = true;
            if (history.pushState) {
              history.pushState(null, null, '#'+$(e.target).attr('href').substr(1));
            } else {
              location.hash = '#'+$(e.target).attr('href').substr(1);
            }
            dont_recurse = false;
          }
        });
        if (location.hash !== '') {
          dont_recurse = true;
          $('a[href="' + location.hash + '"]').tab('show');
          dont_recurse = false;
        }
        $(window).bind('hashchange', function() {
          if (!dont_recurse) {
            dont_recurse = true;
            $('a[href="' + (location.hash || '#release-status') + '"]').tab('show');
            dont_recurse = false;
          }
        });
      });
    </script>
'''


def nice_date(date_string):
    if not arrow:
        return date_string
    # specify format because https://github.com/crsmithdev/arrow/issues/82
    return arrow.get(date_string, 'YYYY-MM-DD HH:mm:ss ZZ').humanize()


def link(url, text, na=None):
    if not url:
        return na if na is not None else text
    if not url.startswith(('http:', 'https:')):
        return '<span title="{}">{}</span>'.format(escape(url, True), text)
    return '<a href="{}">{}</a>'.format(escape(url, True), text)


def image(url, alt):
    if not url:
        return alt
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
    projects = list(projects)
    print(template.format(
        title='Projects',
        javascript=javascript,
        release_status_table=release_status_table_template.format(
            rows='\n'.join(
                release_status_row_template.format(
                    name=link(project.url, escape(project.name)),
                    tag=escape(project.last_tag),
                    date=escape(nice_date(project.last_tag_date)),
                    full_date=escape(project.last_tag_date),
                    build_status=link(project.travis_url,
                                      image(project.travis_image_url, 'Build Status'),
                                      '-'),
                    changes=link(project.compare_url,
                                 escape(pluralize(len(project.pending_commits),
                                                  'commits'))),
                ) for project in projects
            ),
        ),
        maintenance_table=maintenance_table_template.format(
            rows='\n'.join(
                maintenance_table_row_template.format(
                    name=link(project.url, escape(project.name)),
                    build_status=link(project.travis_url,
                                      image(project.travis_image_url, 'Build Status'),
                                      '-'),
                    jenkins_status=link(project.jenkins_url,
                                        image(project.jenkins_image_url, 'Jenkins Status'),
                                        '-'),
                    jenkins_windows_status=link(project.jenkins_url_windows,
                                                image(project.jenkins_image_url_windows, 'Jenkins (Windows)'),
                                                '-'),
                    coveralls_status=link(project.coveralls_url,
                                          image(project.coveralls_image_url, 'Test Coverage'),
                                          '-'),
                ) for project in projects
            ),
        ),
    ))


if __name__ == '__main__':
    main()
