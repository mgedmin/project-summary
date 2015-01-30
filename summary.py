#!/usr/bin/python
"""
Generate a summary for all my projects.
"""

import argparse
import glob
import linecache
import math
import os
import subprocess
import sys
import time
import traceback

import arrow
import mako.template
import mako.exceptions
import requests
import requests_cache


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.8.0dev'

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

class GitHubError(Exception):
    pass


class GitHubRateLimitError(GitHubError):
    pass


def github_request(url):
    res = requests.get(url)
    if res.status_code == 403 and res.headers.get('X-RateLimit-Remaining') == '0':
        reset_time = int(res.headers['X-RateLimit-Reset'])
        minutes = int(math.ceil((reset_time - time.time()) / 60))
        raise GitHubRateLimitError(
            '{message}\nTry again in {minutes} minutes.'.format(
                message=res.json()['message'],
                minutes=minutes))
    elif 400 <= res.status_code < 500:
        raise GitHubError(res.json()['message'])
    return res.json()


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


def get_supported_python_versions(repo_path):
    classifiers = pipe("python", "setup.py", "--classifiers", cwd=repo_path).splitlines()
    prefix = 'Programming Language :: Python :: '
    impl_prefix = 'Programming Language :: Python :: Implementation :: '
    cpython = impl_prefix + 'CPython'
    return [s[len(prefix):] for s in classifiers if s.startswith(prefix)
            and s[len(prefix):len(prefix) + 1].isdigit()] + \
           [s[len(impl_prefix):] for s in classifiers
            if s.startswith(impl_prefix) and s != cpython]


def simplify_python_versions(versions):
    versions = sorted(versions)
    if '2' in versions and any(v.startswith('2.') for v in versions):
        versions.remove('2')
    if '3' in versions and any(v.startswith('3.') for v in versions):
        versions.remove('3')


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
        # Travis has 20px-high SVG images in the new (flat) style
        template = 'https://api.travis-ci.org/{owner}/{name}.svg?branch=master'
        # Shields.io gives me 18px-high SVG and PNG images in the old style
        # and 20px-high in the flat style with ?style=flat
        # but these are slower and sometimes even fail to load
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
        # template = 'https://coveralls.io/repos/{owner}/{name}/badge.png?branch=master'
        # SVG from shields.io (slow/nonfunctional)
        template = 'https://img.shields.io/coveralls/{owner}/{name}.svg?style=flat'
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

    @reify
    def python_versions(self):
        return get_supported_python_versions(self.working_tree)

    @reify
    def open_issues_count(self):
        if not self.is_on_github:
            return None
        url = 'https://api.github.com/repos/{owner}/{name}'.format(
            owner=self.owner, name=self.name)
        # Returns number of issues plus number of pull requests
        return github_request(url)['open_issues_count']

    @reify
    def issues_url(self):
        if not self.is_on_github:
            return None
        return '{base}/issues'.format(base=self.url)


def get_projects():
    for path in get_repos():
        p = Project(path)
        if p.name not in IGNORE and p.last_tag:
            yield p


#
# Templating
#

def mako_error_handler(context, error):
    """Decorate tracebacks when Mako errors happen.

    Evil hack: walk the traceback frames, find compiled Mako templates,
    stuff their (transformed) source into linecache.cache.

    https://gist.github.com/mgedmin/4269249
    """
    rich_tb = mako.exceptions.RichTraceback()
    rich_iter = iter(rich_tb.traceback)
    tb = sys.exc_info()[-1]
    source = {}
    annotated = set()
    while tb is not None:
        cur_rich = next(rich_iter)
        f = tb.tb_frame
        co = f.f_code
        filename = co.co_filename
        lineno = tb.tb_lineno
        if filename.startswith('memory:'):
            lines = source.get(filename)
            if lines is None:
                info = mako.template._get_module_info(filename)
                lines = source[filename] = info.module_source.splitlines(True)
                linecache.cache[filename] = (None, None, lines, filename)
            if (filename, lineno) not in annotated:
                annotated.add((filename, lineno))
                extra = '    # {0} line {1} in {2}:\n    # {3}'.format(*cur_rich)
                lines[lineno - 1] += extra
        tb = tb.tb_next
    # Don't return False -- that will lose the actual Mako frame.  Instead
    # re-raise.
    raise


def Template(*args, **kw):
    return mako.template.Template(error_handler=mako_error_handler,
                                  default_filters=['unicode', 'h'],
                                  *args, **kw)

#
# Report generation
#

template = Template('''\
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <title>Projects</title>

    <link rel="stylesheet" href="assets/css/bootstrap.min.css">

    <style type="text/css">
      td > a > img { position: relative; top: -1px; }
      .tablesorter-icon { color: #ddd; }
      .tablesorter-header { cursor: default; }
      #release-status th:nth-child(3), #release-status td:nth-child(3) { text-align: right; }
      #release-status th:nth-child(4), #release-status td:nth-child(4) { text-align: right; }
      #release-status th:nth-child(5), #release-status td:nth-child(5) { text-align: right; }
      #maintenance th:nth-child(6), #maintenance td:nth-child(6) { text-align: center; }
      #python-versions span.no,
      #python-versions span.yes {
        padding: 2px 4px 3px 4px;
        font-family: DejaVu Sans, Verdana, Geneva, sans-serif;
        font-size: 11px;
        position: relative;
        bottom: 2px;
      }
      #python-versions span.no {
        color: #888;
      }
      #python-versions span.yes {
        color: #fff;
        background-color: #4c1;
        text-shadow: 0px 1px 0px rgba(1, 1, 1, 0.3);
        border-radius: 4px;
      }
      footer { padding-top: 16px; padding-bottom: 16px; text-align: center; color: #999; }
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
          <a class="btn btn-default" data-toggle="tab" href="#python-versions">Python versions</a>
        </div>
        <h1>Projects</h1>
      </div>

      <div class="tab-content">

        <div class="tab-pane active" id="release-status">
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
% for project in projects:
              <tr>
                <td><a href="${project.url}">${project.name}</a></td>
                <td>${project.last_tag}</td>
                <td title="${project.last_tag_date}">${nice_date(project.last_tag_date)}</td>
                <td><a href="${project.compare_url}">${pluralize(len(project.pending_commits), 'commits')}</a></td>
%     if project.travis_url:
                <td><a href="${project.travis_url}"><img src="${project.travis_image_url}" alt="Build Status"></a></td>
%     else:
                <td>-</td>
%     endif
              </tr>
% endfor
            </tbody>
          </table>
        </div>

        <div class="tab-pane" id="maintenance">
          <table class="table table-hover">
            <thead>
              <tr>
                <th>Name</th>
                <th>Travis CI</th>
                <th>Jenkins (Linux)</th>
                <th>Jenkins (Windows)</th>
                <th>Coveralls</th>
                <th>Issues</th>
              </tr>
            </thead>
            <tbody>
% for project in projects:
              <tr>
                <td><a href="${project.url}">${project.name}</a></td>
%     if project.travis_url:
                <td><a href="${project.travis_url}"><img src="${project.travis_image_url}" alt="Build Status"></a></td>
%     else:
                <td>-</td>
%     endif
                <td><a href="${project.jenkins_url}"><img src="${project.jenkins_image_url}" alt="Jenkins Status"></a></td>
                <td><a href="${project.jenkins_url_windows}"><img src="${project.jenkins_image_url_windows}" alt="Jenkins (Windows)"></a></td>
%     if project.coveralls_url:
                <td><a href="${project.coveralls_url}"><img src="${project.coveralls_image_url}" alt="Test Coverage"></a></td>
%     else:
                <td>-</td>
%     endif
                <td><a href="${project.issues_url}">${project.open_issues_count}</a></td>
              </tr>
% endfor
            </tbody>
          </table>
        </div>

        <div class="tab-pane" id="python-versions">
          <% versions = ['2.{}'.format(m) for m in range(4, 7+1)] %>
          <% versions += ['3.{}'.format(m) for m in range(0, 4+1)] %>
          <% versions += ['PyPy'] %>
          <table class="table table-hover">
            <thead>
              <tr>
                <th>Name</th>
% for ver in versions:
                <th>${ver}</th>
% endfor
                <th>Test coverage</th>
              </tr>
            </thead>
            <tbody>
% for project in projects:
              <tr>
                <td><a href="${project.url}">${project.name}</a></td>
%     for ver in versions:
%         if ver in project.python_versions:
                <td><span class="yes">+</span></td>
%         else:
                <td><span class="no">&#x2212;</span></td>
%         endif
%     endfor
%     if project.coveralls_url:
                <td><a href="${project.coveralls_url}"><img src="${project.coveralls_image_url}" alt="Test Coverage"></a></td>
%     else:
                <td>-</td>
%     endif
              </tr>
% endfor
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <footer>
      <div class="container">
        An incomplete list of FOSS projects maintained by <a href="https://github.com/mgedmin">@mgedmin</a>.
        Updated hourly by a <a href="https://jenkins.gedmin.as/job/project-summary/">Jenkins job</a>.
      </div>
    </footer>
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
        $("#python-versions table").tablesorter({
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
  </body>
</html>
''')


def nice_date(date_string):
    # specify format because https://github.com/crsmithdev/arrow/issues/82
    return arrow.get(date_string, 'YYYY-MM-DD HH:mm:ss ZZ').humanize()


def pluralize(number, noun):
    if number == 1:
        assert noun.endswith('s')
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
    parser.add_argument('-o', metavar='FILENAME', dest='output_file',
                        help='write the output to a file (default: stdout)')
    parser.add_argument('--http-cache', default='.httpcache', metavar='DBNAME',
                        # .sqlite will be appended automatically
                        help='cache HTTP requests on disk in an sqlite database (default: .httpcache)')
    parser.add_argument('--no-http-cache', action='store_false', dest='http_cache',
                        help='disable HTTP disk caching')
    args = parser.parse_args()
    if args.http_cache:
        requests_cache.install_cache(args.http_cache,
                                     backend='sqlite',
                                     expire_after=300)

    if args.html:
        try:
            print_html_report(get_projects(), args.output_file)
        except GitHubError as e:
            sys.exit("GitHub error: %s" % e)
        except Exception:
            # if I let CPython print the exception, it'll ignore all of
            # my extra information stuffed into linecache :/
            traceback.print_exc()
            sys.exit(1)
    else:
        if args.output_file:
            print("warning: --output-file ignored in non-HTML mode")
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
            print("  Python versions: {}".format(", ".join(project.python_versions)))
            print("")


def print_html_report(projects, filename=None):
    # I want atomicity: don't destroy old .html file if an exception happens
    # during rendering.
    html = template.render_unicode(projects=list(projects),
                                   nice_date=nice_date,
                                   pluralize=pluralize)
    if filename and filename != '-':
        with open(filename, 'w') as f:
            f.write(html)
    else:
        print(html)


if __name__ == '__main__':
    main()
