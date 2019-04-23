#!/usr/bin/python
"""
Generate a summary for all my projects.
"""

import argparse
import glob
import itertools
import linecache
import logging
import math
import os
import subprocess
import sys
import time
import traceback
from collections import namedtuple

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

try:
    from configparser import SafeConfigParser
except ImportError:
    from ConfigParser import SafeConfigParser

import arrow
import mako.template
import mako.exceptions
import requests
import requests_cache


__author__ = 'Marius Gedminas <marius@gedmin.as>'
__version__ = '0.10.0'

log = logging.getLogger('project-summary')


#
# Utilities
#

class reify(object):
    def __init__(self, fn):
        self.fn = fn

    def __get__(self, obj, cls=None):
        value = self.fn(obj)
        obj.__dict__[self.fn.__name__] = value
        return value


def pipe(*cmd, **kwargs):
    if 'cwd' in kwargs:
        log.debug('EXEC cd %s && %s', kwargs['cwd'], ' '.join(cmd))
    else:
        log.debug('EXEC %s', ' '.join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, **kwargs)
    return p.communicate()[0].decode('UTF-8', 'replace')


def to_seconds(value):
    units = {
        1: ('s', 'sec', 'second', 'seconds'),
        60: ('m', 'min', 'minute', 'minutes'),
        3600: ('h', 'hour', 'hours'),
    }
    s = value.replace(' ', '')
    if s.isdigit():
        return int(s)
    for multiplier, suffixes in units.items():
        for suffix in suffixes:
            if s.endswith(suffix):
                prefix = s[:-len(suffix)]
                if prefix.isdigit():
                    return int(prefix) * multiplier
    raise ValueError('bad time: %s' % value)


#
# Configuration
#

JenkinsJobConfig = namedtuple('JenkinsJobConfig', 'name_template title')
JenkinsJobConfig.__new__.__defaults__ = ('{name}', '')


class Configuration(object):

    _defaults = '''
        [project-summary]
        projects =
        ignore =
        skip-branches = False
        fetch = False
        pull = False
        appveyor-account =
        jenkins-url =
        jenkins-jobs = {name}
        footer = Generated by <a href="https://github.com/mgedmin/project-summary">project-summary</a>.
    '''.replace('\n        ', '\n').strip()

    def __init__(self, filename='project-summary.cfg'):
        cp = SafeConfigParser()
        cp.readfp(StringIO(self._defaults), '<defaults>')
        cp.read([filename])
        self._config = cp

    @reify
    def projects(self):
        return self._config.get('project-summary', 'projects').split()

    @reify
    def ignore(self):
        return self._config.get('project-summary', 'ignore').split()

    @reify
    def skip_branches(self):
        return self._config.getboolean('project-summary', 'skip-branches')

    @reify
    def fetch(self):
        return self._config.getboolean('project-summary', 'fetch')

    @reify
    def pull(self):
        return self._config.getboolean('project-summary', 'pull')

    @reify
    def appveyor_account(self):
        return self._config.get('project-summary', 'appveyor-account')

    @reify
    def jenkins_url(self):
        return self._config.get('project-summary', 'jenkins-url').rstrip('/')

    @reify
    def jenkins_jobs(self):
        return [
            JenkinsJobConfig(*job.split(None, 1))
            for job in self._config.get('project-summary', 'jenkins-jobs').splitlines()
            if job.strip()
        ] if self.jenkins_url else []

    @reify
    def footer(self):
        return self._config.get('project-summary', 'footer')


#
# Data extraction
#

class GitHubError(Exception):
    pass


class GitHubRateLimitError(GitHubError):
    pass


def github_request(url):
    log.debug('GET %s', url)
    res = requests.get(url)
    if res.status_code == 403 and res.headers.get('X-RateLimit-Remaining') == '0':
        reset_time = int(res.headers['X-RateLimit-Reset'])
        minutes = int(math.ceil((reset_time - time.time()) / 60))
        raise GitHubRateLimitError(
            '{message}\nTry again in {minutes} minutes, at {time}.'.format(
                message=res.json()['message'],
                minutes=minutes,
                time=time.strftime('%H:%M', time.localtime(reset_time)),
            ))
    elif 400 <= res.status_code < 500:
        raise GitHubError(res.json()['message'])
    return res


def github_request_json(url):
    return github_request(url).json()


def github_request_list(url, batch_size=100):
    res = github_request('%s?per_page=%d' % (url, batch_size))
    result = res.json()
    for page in itertools.count(2):
        if 'rel="next"' not in res.headers.get('Link', ''):
            break
        res = github_request('%s?per_page=%d&page=%d' % (url, batch_size, page))
        result.extend(res.json())
    return result


#
# Data extraction
#

def get_repos(config):
    return sorted(
        dirname
        for path in config.projects
        for dirname in glob.glob(os.path.expanduser(path))
        if os.path.isdir(os.path.join(dirname, '.git'))
    )


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


def get_branch_name(repo_path):
    name = pipe("git", "rev-parse", "--abbrev-ref", "HEAD",
                cwd=repo_path, stderr=subprocess.PIPE).strip()
    if name != 'HEAD':
        return name
    # detached head, oh my
    commit = pipe("git", "rev-parse", "HEAD",
                  cwd=repo_path, stderr=subprocess.PIPE).strip()
    for line in pipe("git", "show-ref", cwd=repo_path, stderr=subprocess.PIPE).splitlines():
        if line.startswith(commit):
            name = line.split()[1]
            if name.startswith('refs/'):
                name = name[len('refs/'):]
            if name.startswith('heads/'):
                name = name[len('remotes/'):]
            elif name.startswith('remotes/'):
                name = name[len('remotes/'):]
                if name.startswith('origin/'):
                    name = name[len('origin/'):]
            if name != 'HEAD':
                return name
    # okay, we have a _stale_ detached head, Jenkins must be dropping
    # github notifications again!
    for line in pipe("git", "branch", "-r", "--contains", name, cwd=repo_path, stderr=subprocess.PIPE).splitlines():
        name = line[2:].strip()
        if name.startswith('origin/'):
            name = name[len('origin/'):]
        if 'HEAD detached at' not in name:
            return name
    return '(detached)'


def get_last_tag(repo_path):
    return pipe("git", "describe", "--tags", "--abbrev=0",
                cwd=repo_path, stderr=subprocess.PIPE).strip()


def get_date_of_tag(repo_path, tag):
    return pipe("git", "log", "-1", "--format=%ai", tag, cwd=repo_path).strip()


def get_pending_commits(repo_path, last_tag, branch='master'):
    return pipe("git", "log", "--oneline", "{}..origin/{}".format(last_tag, branch),
                cwd=repo_path).splitlines()


def get_supported_python_versions(repo_path):
    classifiers = pipe(sys.executable, "setup.py", "--classifiers",
                       cwd=repo_path, stderr=subprocess.PIPE).splitlines()
    prefix = 'Programming Language :: Python :: '
    impl_prefix = 'Programming Language :: Python :: Implementation :: '
    cpython = impl_prefix + 'CPython'
    return [
        s[len(prefix):]
        for s in classifiers
        if s.startswith(prefix) and s[len(prefix):len(prefix) + 1].isdigit()
    ] + [
        s[len(impl_prefix):]
        for s in classifiers
        if s.startswith(impl_prefix) and s != cpython
    ]


def simplify_python_versions(versions):
    versions = sorted(versions)
    if '2' in versions and any(v.startswith('2.') for v in versions):
        versions.remove('2')
    if '3' in versions and any(v.startswith('3.') for v in versions):
        versions.remove('3')


class Project(object):

    def __init__(self, working_tree, config):
        self.working_tree = working_tree
        self.config = config

    def fetch(self):
        pipe('git', 'fetch', '--prune', cwd=self.working_tree)

    def pull(self):
        pipe('git', 'pull', '--prune', cwd=self.working_tree)

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

    @reify
    def uses_appveyor(self):
        if not self.is_on_github or not self.config.appveyor_account:
            return False
        return os.path.exists(os.path.join(self.working_tree, 'appveyor.yml'))

    @property
    def uses_jenkins(self):
        return bool(self.config.jenkins_url)

    @reify
    def branch(self):
        return get_branch_name(self.working_tree)

    @reify
    def last_tag(self):
        return get_last_tag(self.working_tree)

    @reify
    def last_tag_date(self):
        return get_date_of_tag(self.working_tree, self.last_tag)

    @reify
    def pending_commits(self):
        return get_pending_commits(self.working_tree, self.last_tag, self.branch)

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
    def pypi_url(self):
        return 'https://pypi.org/project/{name}/'.format(name=self.name)

    @property
    def jenkins_job(self):
        if os.path.basename(self.working_tree) == 'workspace':
            return os.path.basename(os.path.dirname(self.working_tree))
        else:
            return os.path.basename(self.working_tree)

    @property
    def compare_url(self):
        if not self.is_on_github:
            return None
        return '{base}/compare/{tag}...{branch}'.format(base=self.url,
                                                        branch=self.branch,
                                                        tag=self.last_tag)

    @property
    def travis_image_url(self):
        if not self.uses_travis:
            return None
        # Travis has 20px-high SVG images in the new (flat) style
        template = 'https://api.travis-ci.org/{owner}/{name}.svg?branch={branch}'
        # Shields.io gives me 18px-high SVG and PNG images in the old style
        # and 20px-high in the flat style with ?style=flat
        # but these are slower and sometimes even fail to load
        # template = '//img.shields.io/travis/{owner}/{name}/master.svg'
        return template.format(name=self.name, owner=self.owner, branch=self.branch)

    @property
    def travis_url(self):
        if not self.uses_travis:
            return None
        return 'https://travis-ci.org/{owner}/{name}'.format(name=self.name,
                                                             owner=self.owner)

    @property
    def appveyor_image_url(self):
        if not self.uses_appveyor:
            return None
        template = 'https://ci.appveyor.com/api/projects/status/github/{owner}/{name}?branch={branch}&svg=true'
        return template.format(name=self.name, owner=self.owner, branch=self.branch)

    @property
    def appveyor_url(self):
        if not self.uses_appveyor:
            return None
        return 'https://ci.appveyor.com/project/{account}/{name}/branch/{branch}'.format(
            name=self.name, account=self.config.appveyor_account, branch=self.branch)

    @property
    def coveralls_image_url(self):
        if not self.uses_travis:
            return None
        # 18px-high PNG
        # template = 'https://coveralls.io/repos/{owner}/{name}/badge.png?branch=master'
        # 20px-high flat SVG
        template = 'https://coveralls.io/repos/{owner}/{name}/badge.svg?branch={branch}'
        # SVG from shields.io (slow)
        # template = 'https://img.shields.io/coveralls/{owner}/{name}.svg?style=flat'
        return template.format(name=self.name, owner=self.owner, branch=self.branch)

    @property
    def coveralls_url(self):
        if not self.uses_travis:
            return None
        return 'https://coveralls.io/r/{owner}/{name}?branch={branch}'.format(
            name=self.name, owner=self.owner, branch=self.branch)

    @reify
    def coverage_number(self):
        url = self.coveralls_image_url
        if not url:
            return None
        log.debug('GET %s', url)
        res = requests.get(url, allow_redirects=False)
        location = res.headers.get('Location')
        if res.status_code != 302 or not location:
            return None
        PREFIX = 'https://s3.amazonaws.com/assets.coveralls.io/badges/coveralls_'
        SUFFIX = '.svg'
        if location.startswith(PREFIX) and location.endswith(SUFFIX):
            coverage = location[len(PREFIX):-len(SUFFIX)]
            if coverage.isdigit():  # could be 'unknown'
                return int(coverage)
        return None

    def coverage(self, format='{}', unknown='-1'):
        if self.coverage_number is None:
            return unknown
        else:
            return format.format(self.coverage_number)

    def get_jenkins_image_url(self, job_config=JenkinsJobConfig()):
        if not self.uses_jenkins:
            return None
        return '{base}/job/{name}/badge/icon'.format(
            base=self.config.jenkins_url,
            name=job_config.name_template.format(name=self.jenkins_job),
        )

    def get_jenkins_url(self, job_config=JenkinsJobConfig()):
        if not self.uses_jenkins:
            return None
        return '{base}/job/{name}/'.format(
            base=self.config.jenkins_url,
            name=job_config.name_template.format(name=self.jenkins_job),
        )

    @reify
    def python_versions(self):
        return get_supported_python_versions(self.working_tree)

    @reify
    def github_issues_and_pulls(self):
        if not self.is_on_github:
            return []
        url = 'https://api.github.com/repos/{owner}/{name}/issues'.format(
            owner=self.owner, name=self.name)
        return github_request_list(url)

    @reify
    def github_issues(self):
        return [issue for issue in self.github_issues_and_pulls
                if 'pull_request' not in issue]

    @reify
    def github_pulls(self):
        return [issue for issue in self.github_issues_and_pulls
                if 'pull_request' in issue]

    @reify
    def open_issues_count(self):
        return len(self.github_issues)

    @reify
    def unlabeled_open_issues_count(self):
        return sum(1 for issue in self.github_issues if not issue['labels'])

    @reify
    def issues_url(self):
        if not self.is_on_github:
            return None
        return '{base}/issues'.format(base=self.url)

    @reify
    def open_pulls_count(self):
        return len(self.github_pulls)

    @reify
    def unlabeled_open_pulls_count(self):
        return sum(1 for issue in self.github_pulls if not issue['labels'])

    @reify
    def pulls_url(self):
        if not self.is_on_github:
            return None
        return '{base}/pulls'.format(base=self.url)


def get_projects(config):
    for path in get_repos(config):
        p = Project(path, config)
        if p.name in config.ignore:
            continue
        if config.skip_branches and p.branch != 'master':
            continue
        if config.fetch:
            p.fetch()
        if config.pull:
            p.pull()
        if p.last_tag:
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
                                  strict_undefined=True,
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
      th { white-space: nowrap; }
      td > a > img { position: relative; top: -1px; }
      .tablesorter-icon { color: #ddd; }
      .tablesorter-header { cursor: default; }
      .invisible { visibility: hidden; }
      #release-status th:nth-child(3), #release-status td:nth-child(3) { text-align: right; }
      #release-status th:nth-child(4), #release-status td:nth-child(4) { text-align: right; }
      #release-status th:nth-child(5), #release-status td:nth-child(5) { text-align: right; }
      #maintenance th:nth-child(7), #maintenance td:nth-child(7) { text-align: right; }
      #maintenance th:nth-child(8), #maintenance td:nth-child(8) { text-align: right; }
      #maintenance span.new { font-weight: bold; }
      #maintenance span.none { color: #999; }
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

<%def name="project_name(project)">\\
<a href="${project.url}">${project.name}</a>\\
% if project.branch != 'master':
 (${project.branch})\\
% endif
</%def>

<%def name="issues(new_count, total_count, url)">\\
<a href="${url}" title="${new_count} new, ${total_count} total">\\
% if new_count == 0:
<span class="none">${new_count}</span> \\
% else:
<span class="new">${new_count}</span> \\
% endif
% if total_count == 0:
<span class="none">(${total_count})</span>\\
% else:
(${total_count})\\
% endif
</a>\\
</%def>

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
                <td>${project_name(project)}</td>
                <td><a href="${project.pypi_url}">${project.last_tag}</a></td>
                <td title="${project.last_tag_date}">${nice_date(project.last_tag_date)}</td>
                <td><a href="${project.compare_url}">${pluralize(len(project.pending_commits), 'commits')}</a></td>
%     if project.travis_url:
                <td><a href="${project.travis_url}"><img src="${project.travis_image_url}" alt="Build Status" height="20"></a></td>
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
            <colgroup>
              <col width="15%">
              <col width="15%">
% for job in config.jenkins_jobs:
              <col width="15%">
% endfor
              <col width="15%">
              <col width="15%">
              <col width="5%">
              <col width="5%">
            </colgroup>
            <thead>
              <tr>
                <th>Name</th>
                <th>Travis CI</th>
% for job in config.jenkins_jobs:
                <th>Jenkins ${job.title}</th>
% endfor
                <th>Appveyor</th>
                <th>Coveralls</th>
                <th>Issues</th>
                <th>PRs</th>
              </tr>
            </thead>
            <tbody>
% for project in projects:
              <tr>
                <td>${project_name(project)}</td>
%     if project.travis_url:
                <td><a href="${project.travis_url}"><img src="${project.travis_image_url}" alt="Build Status" height="20"></a></td>
%     else:
                <td>-</td>
%     endif
% for job in config.jenkins_jobs:
%     if project.uses_jenkins:
                <td><a href="${project.get_jenkins_url(job)}"><img src="${project.get_jenkins_image_url(job)}" alt="Jenkins Status" height="20"></a></td>
%     else:
                <td>-</td>
%     endif
% endfor
%     if project.appveyor_url:
                <td><a href="${project.appveyor_url}"><img src="${project.appveyor_image_url}" alt="Build Status (Windows)" height="20"></a></td>
%     else:
                <td>-</td>
%     endif
%     if project.coveralls_url:
                <td data-coverage="${project.coverage()}"><a href="${project.coveralls_url}"><img src="${project.coveralls_image_url}" alt="Test Coverage: ${project.coverage('{}%', 'unknown')}" height="20"></a></td>
%     else:
                <td>-</td>
%     endif
%     for new_count, total_count, url in [(project.unlabeled_open_issues_count, project.open_issues_count, project.issues_url), (project.unlabeled_open_pulls_count, project.open_pulls_count, project.pulls_url)]:
                <td data-total="${total_count}" data-new=${new_count}>${issues(new_count, total_count, url)}</td>
%     endfor
              </tr>
% endfor
            </tbody>
          </table>
        </div>

<% versions = ['2.7', '3.5', '3.6', '3.7', 'PyPy'] %>
        <div class="tab-pane" id="python-versions">
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
                <td>${project_name(project)}</td>
%     for ver in versions:
%         if ver in project.python_versions:
                <td><span class="yes">+</span></td>
%         else:
                <td><span class="no">&#x2212;</span></td>
%         endif
%     endfor
%     if project.coveralls_url:
                <td data-coverage="${project.coverage()}"><a href="${project.coveralls_url}"><img src="${project.coveralls_image_url}" alt="Test Coverage: ${project.coverage('{}%', 'unknown')}" height="20"></a></td>
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
        ${config.footer|n}
      </div>
    </footer>
    <script src="assets/js/jquery.min.js"></script>
    <script src="assets/js/jquery.tablesorter.min.js"></script>
    <script src="assets/js/jquery.tablesorter.widgets.min.js"></script>
    <script src="assets/js/bootstrap.min.js"></script>
    <script>
      $(function() {
        $.extend($.tablesorter.themes.bootstrap, {
            table        : '',
            caption      : '',
            header       : '',
            footerRow    : '',
            footerCells  : '',
            sortNone     : '',
            sortAsc      : '',
            sortDesc     : '',
            active       : '',
            hover        : 'active',
            icons        : '',
            iconSortNone : 'glyphicon glyphicon-sort invisible',
            iconSortAsc  : 'glyphicon glyphicon-sort-by-attributes',
            iconSortDesc : 'glyphicon glyphicon-sort-by-attributes-alt',
            filterRow    : '',
            footerRow    : '',
            footerCells  : '',
            even         : '',
            odd          : ''
          });
        $("#release-status table").tablesorter({
          theme: "bootstrap",
          widgets: ['uitheme'],
          widthFixed: true,
          headerTemplate: ' {content} {icon}',
          onRenderHeader: function(idx, config, table) {
            if (idx >= 2) {
              var $this = $(this);
              $this.find('div').prepend($this.find('i'));
            }
          },
          sortList: [[0, 0]],
          textExtraction: {
            2: function(node, table, cellIndex) { return $(node).attr('title'); }
          }
        });
        var sortCoverage = function(node, table, cellIndex) {
          return $(node).attr('data-coverage');
        };
        var sortIssues = function(node, table, cellIndex) {
          /* note this can't start with a digit or tablesorter will discard the 2nd sort key */
          return 'new ' + $(node).attr('data-new') + ' old ' + $(node).attr('data-total');
        };
        $("#maintenance table").tablesorter({
          theme: "bootstrap",
          widgets: ['uitheme'],
          widthFixed: true,
          headerTemplate: ' {content} {icon}',
          onRenderHeader: function(idx, config, table) {
            if (idx >= 6) {
              var $this = $(this);
              $this.find('div').prepend($this.find('i'));
            }
          },
          sortList: [[0, 0]],
          textExtraction: {
            5: sortCoverage,
            6: sortIssues,
            7: sortIssues
          }
        });
        $("#python-versions table").tablesorter({
          theme: "bootstrap",
          widgets: ['uitheme'],
          widthFixed: true,
          headerTemplate: '{content} {icon}',
          sortList: [[0, 0]],
          textExtraction: {
            ${1 + len(versions)}: function(node, table, cellIndex) { return $(node).attr('data-coverage'); }
          }
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
    config = Configuration()
    parser = argparse.ArgumentParser(
        description="Summarize release status of several projects")
    parser.add_argument('--version', action='version',
                        version="%(prog)s version " + __version__)
    parser.add_argument('-v', '--verbose', action='count',
                        help='be more verbose (can be repeated)')
    parser.add_argument('--skip-branches', action='store_true',
                        help="ignore checkouts that aren't of the main branch")
    parser.add_argument('--html', action='store_true',
                        help='produce HTML output')
    parser.add_argument('-o', metavar='FILENAME', dest='output_file',
                        help='write the output to a file (default: stdout)')
    parser.add_argument('--http-cache', default='.httpcache', metavar='DBNAME',
                        # .sqlite will be appended automatically
                        help='cache HTTP requests on disk in an sqlite database (default: %(default)s)')
    parser.add_argument('--no-http-cache', action='store_false', dest='http_cache',
                        help='disable HTTP disk caching')
    parser.add_argument('--cache-duration', default='15m',
                        help='how long to cache HTTP requests (default: %(default)s)')
    parser.add_argument('--fetch', '--update', action='store_true',
                        help='run git fetch in each project')
    parser.add_argument('--pull', action='store_true',
                        help='run git pull in each project')
    args = parser.parse_args()

    log.addHandler(logging.StreamHandler())
    log.setLevel(logging.DEBUG if args.verbose >= 3 else
                 logging.INFO if args.verbose >= 1 else
                 logging.ERROR)

    if args.http_cache:
        log.debug('caching HTTP requests for %s', args.cache_duration)
        requests_cache.install_cache(
            args.http_cache,
            backend='sqlite',
            expire_after=to_seconds(args.cache_duration)
        )

    if args.fetch is not None:
        config.fetch = args.fetch
    if args.pull is not None:
        config.pull = args.pull
    if args.skip_branches is not None:
        config.skip_branches = args.skip_branches
    projects = get_projects(config)
    if args.html:
        try:
            print_html_report(projects, config, args.output_file)
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
        print_report(projects, args.verbose)


def print_report(projects, verbose):
    for project in projects:
        print("{name:24} {commits:4} commits since {release:6} ({date})".format(
            name=project.name, commits=len(project.pending_commits),
            release=project.last_tag, date=nice_date(project.last_tag_date)))
        if verbose >= 1:
            print("  {}".format(project.compare_url))
            if verbose >= 2:
                print("  {}".format(project.working_tree))
            print("  Python versions: {}".format(", ".join(project.python_versions)))
            print("")


def print_html_report(projects, config, filename=None):
    # I want atomicity: don't destroy old .html file if an exception happens
    # during rendering.
    html = template.render_unicode(projects=list(projects),
                                   config=config,
                                   nice_date=nice_date,
                                   pluralize=pluralize)
    if filename and filename != '-':
        with open(filename, 'w') as f:
            f.write(html)
    else:
        print(html)


if __name__ == '__main__':
    main()
