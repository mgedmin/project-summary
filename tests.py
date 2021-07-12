import datetime
import json
import logging
import subprocess
import sys
import textwrap
import time
import traceback

import markupsafe
import pypistats
import pytest
import requests
import requests_cache
from requests.exceptions import ConnectionError, HTTPError

import summary
from summary import (
    AppveyorColumn,
    BuildStatusColumn,
    CSS,
    ChangesColumn,
    Column,
    Configuration,
    CoverallsColumn,
    DataColumn,
    DateColumn,
    GitHubActionsColumn,
    GitHubError,
    GitHubRateLimitError,
    IssuesColumn,
    JenkinsColumn,
    JenkinsJobConfig,
    NameColumn,
    Page,
    Pages,
    Project,
    PullsColumn,
    PypiStatsColumn,
    PythonSupportColumn,
    StatusColumn,
    Template,
    TravisColumn,
    VersionColumn,
    _filter_projects,
    format_cmd,
    get_branch_name,
    get_date_of_tag,
    get_last_tag,
    get_pending_commits,
    get_project_name,
    get_project_owner,
    get_projects,
    get_repo_url,
    get_report_pages,
    get_repos,
    get_supported_python_versions,
    github_request,
    github_request_list,
    html,
    is_cached,
    log_url,
    nice_date,
    normalize_github_url,
    pipe,
    pluralize,
    print_html_report,
    print_report,
    reify,
    symlink_assets,
    to_seconds,
)


TRAVIS_STATUS_ICON_BUILD_PASSING = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="90" height="20">'
    '<linearGradient id="a" x2="0" y2="100%">'
    '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
    '<stop offset="1" stop-opacity=".1"/>'
    '</linearGradient>'
    '<rect rx="3" width="90" height="20" fill="#555"/>'
    '<rect rx="3" x="37" width="53" height="20" fill="#4c1"/>'
    '<path fill="#4c1" d="M37 0h4v20h-4z"/>'
    '<rect rx="3" width="90" height="20" fill="url(#a)"/>'
    '<g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">'
    '<text x="19.5" y="15" fill="#010101" fill-opacity=".3">build</text>'
    '<text x="19.5" y="14">build</text>'
    '<text x="62.5" y="15" fill="#010101" fill-opacity=".3">passing</text>'
    '<text x="62.5" y="14">passing</text>'
    '</g>'
    '</svg>'
)

APPVEYOR_STATUS_ICON_BUILD_PASSING = '''\
<svg xmlns="http://www.w3.org/2000/svg" width="106" height="20" style="shape-rendering:geometricPrecision; image-rendering:optimizeQuality; fill-rule:evenodd; clip-rule:evenodd">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="a">
    <rect width="106" height="20" rx="3" fill="#fff"/>
  </mask>
  <g mask="url(#a)">
    <path fill="#555" d="M0 0h53v20H0z"/>
    <path fill="#4c1" d="M53 0h84v20H53z"/>
    <path fill="url(#b)" d="M0 0h106v20H0z"/>
  </g>
  <g transform="matrix(0.045,0,0,0.045,0,1.0227272)">
    <path fill="#ccc" d="M242 48c86,0 155,69 155,154 0,86 -69,155 -155,155 -85,0 -154,-69 -154,-155 0,-85 69,-154 154,-154zm38 184c-17,22 -48,26 -69,9 -21,-16 -24,-47 -7,-69 18,-21 49,-25 70,-9 21,17 24,48 6,69zm-82 101l59 -57c-22,5 -45,1 -63,-14 -21,-16 -30,-43 -27,-68l-53 58c0,0 -7,-13 -9,-37l93 -73c28,-20 66,-21 93,0 30,24 36,68 14,101l-68 97c-10,0 -30,-3 -39,-7z"/>
  </g>
  <g fill="#fff" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">

    <text x="22" y="15" fill="#010101" fill-opacity=".3">build</text>
    <text x="22" y="14">build</text>

    <text x="58" y="15" fill="#010101" fill-opacity=".3">passing</text>
    <text x="58" y="14">passing</text>
  </g>
</svg>
'''

JENKINS_STATUS_ICON_BUILD_PASSING = '''\
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="110.0" height="20">
    <linearGradient id="a" x2="0" y2="100%">
        <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
        <stop offset="1" stop-opacity=".1"/>
    </linearGradient>
    <rect rx="3" width="110.0" height="20" fill="#555"/>
    <rect rx="0" x="47.0" width="4" height="20" fill="#44cc11"/>
    <rect rx="3" x="47.0" width="63.0" height="20" fill="#44cc11"/>
    <rect rx="3" width="110.0" height="20" fill="url(#a)"/>
    <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
        <text x="24.5" y="15" fill="#010101" fill-opacity=".3">build</text>
        <text x="24.5" y="14">build</text>
        <text x="77.5" y="15" fill="#010101" fill-opacity=".3">passing</text>
        <text x="77.5" y="14">passing</text>
    </g>
</svg>
'''

GHA_STATUS_ICON_BUILD_PASSING = '''\
<svg xmlns="http://www.w3.org/2000/svg" width="104" height="20">
  <defs>
    <linearGradient id="workflow-fill" x1="50%" y1="0%" x2="50%" y2="100%">
      <stop stop-color="#444D56" offset="0%"></stop>
      <stop stop-color="#24292E" offset="100%"></stop>
    </linearGradient>
    <linearGradient id="state-fill" x1="50%" y1="0%" x2="50%" y2="100%">
      <stop stop-color="#34D058" offset="0%"></stop>
      <stop stop-color="#28A745" offset="100%"></stop>
    </linearGradient>
  </defs>
  <g fill="none" fill-rule="evenodd">
    <g font-family="&#39;DejaVu Sans&#39;,Verdana,Geneva,sans-serif" font-size="11">
      <path id="workflow-bg" d="M0,3 C0,1.3431 1.3552,0 3.02702703,0 L54,0 L54,20 L3.02702703,20 C1.3552,20 0,18.6569 0,17 L0,3 Z" fill="url(#workflow-fill)" fill-rule="nonzero"></path>
      <text fill="#010101" fill-opacity=".3">
        <tspan x="22.1981982" y="15">build</tspan>
      </text>
      <text fill="#FFFFFF">
        <tspan x="22.1981982" y="14">build</tspan>
      </text>
    </g>
    <g transform="translate(54)" font-family="&#39;DejaVu Sans&#39;,Verdana,Geneva,sans-serif" font-size="11">
      <path d="M0 0h46.939C48.629 0 50 1.343 50 3v14c0 1.657-1.37 3-3.061 3H0V0z" id="state-bg" fill="url(#state-fill)" fill-rule="nonzero"></path>
      <text fill="#010101" fill-opacity=".3">
        <tspan x="4" y="15">passing</tspan>
      </text>
      <text fill="#FFFFFF">
        <tspan x="4" y="14">passing</tspan>
      </text>
    </g>
    <path fill="#959DA5" d="M11 3c-3.868 0-7 3.132-7 7a6.996 6.996 0 0 0 4.786 6.641c.35.062.482-.148.482-.332 0-.166-.01-.718-.01-1.304-1.758.324-2.213-.429-2.353-.822-.079-.202-.42-.823-.717-.99-.245-.13-.595-.454-.01-.463.552-.009.946.508 1.077.718.63 1.058 1.636.76 2.039.577.061-.455.245-.761.446-.936-1.557-.175-3.185-.779-3.185-3.456 0-.762.271-1.392.718-1.882-.07-.175-.315-.892.07-1.855 0 0 .586-.183 1.925.718a6.5 6.5 0 0 1 1.75-.236 6.5 6.5 0 0 1 1.75.236c1.338-.91 1.925-.718 1.925-.718.385.963.14 1.68.07 1.855.446.49.717 1.112.717 1.882 0 2.686-1.636 3.28-3.194 3.456.254.219.473.639.473 1.295 0 .936-.009 1.689-.009 1.925 0 .184.131.402.481.332A7.011 7.011 0 0 0 18 10c0-3.867-3.133-7-7-7z"></path>
  </g>
</svg>
'''


class SomethingThatUsesReify:

    computations = 0

    @reify
    def computo_ergo_sum(self):
        self.computations += 1
        return 2 * 2


def test_reify(capsys):
    sth = SomethingThatUsesReify()
    assert sth.computo_ergo_sum == 4
    assert sth.computations == 1


def test_reify_caches(capsys):
    sth = SomethingThatUsesReify()
    assert sth.computo_ergo_sum == 4
    assert sth.computo_ergo_sum == 4
    assert sth.computo_ergo_sum == 4
    assert sth.computations == 1


def test_reify_cache_can_be_invalidated(capsys):
    sth = SomethingThatUsesReify()
    assert sth.computo_ergo_sum == 4
    del sth.computo_ergo_sum
    assert sth.computo_ergo_sum == 4
    assert sth.computations == 2


def test_reify_cache_can_be_overridden(capsys):
    sth = SomethingThatUsesReify()
    assert sth.computo_ergo_sum == 4
    sth.computo_ergo_sum = 5
    assert sth.computo_ergo_sum == 5
    assert sth.computations == 1


def test_reify_cache_is_per_instance(capsys):
    sth = SomethingThatUsesReify()
    other = SomethingThatUsesReify()
    assert sth.computo_ergo_sum == 4
    sth.computo_ergo_sum = 5
    assert other.computo_ergo_sum == 4
    assert sth.computations == 1
    assert other.computations == 1


def test_format_cmd():
    assert format_cmd(['git', 'log']) == 'git log'


def test_format_cmd_with_working_dir_change():
    assert format_cmd(['git', 'log'], cwd='/path') == 'cd /path && git log'


def test_pipe():
    assert pipe('echo', 'hi') == 'hi\n'


def test_pipe_warn_on_failure():
    assert pipe('false') == ''


def test_pipe_warn_on_stderr():
    assert pipe('sh', '-c', 'echo boo 1>&2', stderr=subprocess.PIPE) == ''


@pytest.mark.parametrize(['input', 'expected'], [
    ('30', 30),
    ('30s', 30),
    ('30 sec', 30),
    ('30 seconds', 30),
    ('1 second', 1),
    ('5m', 5 * 60),
    ('5 min', 5 * 60),
    ('5 minutes', 5 * 60),
    ('1 minute', 60),
    ('2h', 2 * 60 * 60),
    ('2 hours', 2 * 60 * 60),
    ('1 hour', 60 * 60),
])
def test_to_seconds(input, expected):
    assert to_seconds(input) == expected


def test_to_seconds_error():
    with pytest.raises(ValueError):
        to_seconds('uhh')


def test_Configuration_defaults():
    cfg = Configuration('/dev/null')
    assert cfg.projects == []
    assert cfg.ignore == []
    assert cfg.skip_branches is False
    assert cfg.fetch is False
    assert cfg.pull is False
    assert cfg.gha_workflow_name == 'build'
    assert cfg.appveyor_account == ''
    assert cfg.jenkins_url == ''
    assert cfg.jenkins_jobs == []
    assert cfg.footer == markupsafe.Markup(
        'Generated by <a href="https://github.com/mgedmin/project-summary">project-summary</a>.'
    )
    assert cfg.pypi_name_map == {}
    assert cfg.python_versions == ['2.7', '3.6', '3.7', '3.8', '3.9', 'PyPy']


def test_Configuration_projects(tmp_path):
    tmp_path.joinpath('test.cfg').write_text(textwrap.dedent('''
        [project-summary]
        projects =
          foo
          bar
    '''))
    cfg = Configuration(tmp_path / 'test.cfg')
    assert cfg.projects == ['foo', 'bar']


def test_Configuration_ignore(tmp_path):
    tmp_path.joinpath('test.cfg').write_text(textwrap.dedent('''
        [project-summary]
        ignore =
          foo
          bar
    '''))
    cfg = Configuration(tmp_path / 'test.cfg')
    assert cfg.ignore == ['foo', 'bar']


def test_Configuration_jenkins_url_strips_trailing_slash(tmp_path):
    tmp_path.joinpath('test.cfg').write_text(textwrap.dedent('''
        [project-summary]
        jenkins-url = https://jenkins.example.com/
    '''))
    cfg = Configuration(tmp_path / 'test.cfg')
    assert cfg.jenkins_url == 'https://jenkins.example.com'


def test_Configuration_jenkins_jobs_default(tmp_path):
    tmp_path.joinpath('test.cfg').write_text(textwrap.dedent('''
        [project-summary]
        jenkins-url = https://jenkins.example.com/
    '''))
    cfg = Configuration(tmp_path / 'test.cfg')
    assert cfg.jenkins_jobs == [JenkinsJobConfig('{name}')]


def test_Configuration_jenkins_jobs(tmp_path):
    tmp_path.joinpath('test.cfg').write_text(textwrap.dedent('''
        [project-summary]
        jenkins-url = https://jenkins.example.com/
        jenkins-jobs =
           {name}-on-linux    Linux
           {name}-on-windows  Windows
    '''))
    cfg = Configuration(tmp_path / 'test.cfg')
    assert cfg.jenkins_jobs == [
        JenkinsJobConfig('{name}-on-linux', 'Linux'),
        JenkinsJobConfig('{name}-on-windows', 'Windows'),
    ]


def test_Configuration_pypi_name_map(tmp_path):
    tmp_path.joinpath('test.cfg').write_text(textwrap.dedent('''
        [project-summary]
        pypi-name-map =
           foo: bar
    '''))
    cfg = Configuration(tmp_path / 'test.cfg')
    assert cfg.pypi_name_map == {
        'foo': 'bar',
    }


def test_Configuration_allows_underscores_or_dashes(tmp_path):
    tmp_path.joinpath('test.cfg').write_text(textwrap.dedent('''
        [project-summary]
        pypi-name_map =
           foo: bar
    '''))
    cfg = Configuration(tmp_path / 'test.cfg')
    assert cfg.pypi_name_map == {
        'foo': 'bar',
    }


def test_is_cached_no_cache():
    session = requests.Session()
    assert not is_cached('https://example.com', session)


def test_is_cached_empty_cache():
    session = requests_cache.CachedSession(backend='memory')
    assert not is_cached('https://example.com', session)


def add_to_cache(url, session):
    request = session.prepare_request(requests.Request('GET', url))
    cache_key = session.cache.create_key(request)
    response = requests.Response()
    response.request = request
    session.cache.save_response(response, cache_key)


def test_is_cached_has_cache_but_no_expiration():
    session = requests_cache.CachedSession(backend='memory')
    url = 'https://example.com'
    add_to_cache(url, session)
    assert is_cached(url, session)


def test_is_cached_has_cache_not_expired():
    session = requests_cache.CachedSession(
        backend='memory', expire_after=datetime.timedelta(minutes=15))
    url = 'https://example.com'
    add_to_cache(url, session)
    assert is_cached(url, session)


def test_log_url_cache_miss(caplog):
    caplog.set_level(logging.DEBUG)
    session = requests.Session()
    log_url("http://example.com", session)
    assert caplog.messages == ['GET http://example.com']


def test_log_url_cache_hit(caplog):
    caplog.set_level(logging.DEBUG, logger='project-summary')
    session = requests_cache.CachedSession(backend='memory')
    add_to_cache('http://example.com', session)
    log_url("http://example.com", session)
    assert caplog.messages == ['HIT http://example.com']


class MockSession:

    def __init__(self, prototype=None):
        if isinstance(prototype, dict):
            self._prototype = prototype
        else:
            self._prototype = {
                None: prototype or MockResponse()
            }

    def get(self, url, allow_redirects=True, headers=None):
        prototype = self._prototype.get(url)
        if prototype is None:
            prototype = self._prototype.get(None)
        if prototype is None:
            return MockResponse()
        return prototype._copy()


class MockResponse:

    def __init__(self, status_code=200, text=None, *, json=None, headers=None):
        self.status_code = status_code
        if json is not None:
            self.text = _json_dumps(json)
        elif text is not None:
            self.text = text
        else:
            self.text = '{}'
        self.headers = {}
        if headers:
            self.headers.update(headers)

    def _copy(self):
        return MockResponse(
            status_code=self.status_code, text=self.text, headers=self.headers)

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


_json_dumps = json.dumps


def test_github_request():
    session = MockSession()
    response = github_request('http://example.com/', session)
    assert response.status_code == 200


def test_github_request_json_error():
    session = MockSession(MockResponse(text='not json'))
    with pytest.raises(GitHubError):
        github_request('http://example.com/', session)


def test_github_request_error():
    session = MockSession(MockResponse(400, json={"message": "oopie wopsie"}))
    with pytest.raises(GitHubError):
        github_request('http://example.com/', session)


def test_github_request_rate_limit():
    session = MockSession(MockResponse(
        status_code=403,
        json={"message": "slow it down pls"},
        headers={
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset': str(int(time.time() + 60)),
        },
    ))
    with pytest.raises(GitHubRateLimitError):
        github_request('http://example.com/', session)


def test_github_request_list():
    session = MockSession(MockResponse(
        json=[{'a': 2}],
    ))
    result = github_request_list('http://example.com/items', session)
    assert result == [{'a': 2}]


def test_github_request_list_pages():
    session = MockSession({
        'http://example.com/items?per_page=100': MockResponse(
            json=[{'a': 2}],
            headers={
                'Link': '</items?per_page=100&page=2>; rel="next"',
            }
        ),
        'http://example.com/items?per_page=100&page=2': MockResponse(
            json=[{'b': 3}],
        ),
    })
    result = github_request_list('http://example.com/items', session)
    assert result == [{'a': 2}, {'b': 3}]


def test_get_repos(tmp_path, config):
    (tmp_path / 'a' / '.git').mkdir(parents=True)
    config._config.set('project-summary', 'projects', str(tmp_path / '*'))
    assert get_repos(config) == [str(tmp_path / 'a')]


def test_get_repo_url_not_git_repo(tmp_path):
    assert not get_repo_url(tmp_path)


def test_get_repo_url_no_remotes(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    assert not get_repo_url(tmp_path)


def test_get_repo_url_no_origin(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    subprocess.run(['git', 'remote', 'add', 'example', 'https://example.com'],
                   cwd=tmp_path)
    assert not get_repo_url(tmp_path)


def test_get_repo_url(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    subprocess.run(['git', 'remote', 'add', 'origin', 'https://example.com'],
                   cwd=tmp_path)
    assert get_repo_url(tmp_path) == 'https://example.com'


@pytest.mark.parametrize('url, expected', [
    (None, None),
    ('', ''),
    ('git://github.com/mgedmin/project-summary.git',
     'https://github.com/mgedmin/project-summary'),
    ('git@github.com:mgedmin/project-summary.git',
     'https://github.com/mgedmin/project-summary'),
    ('https://github.com/mgedmin/project-summary',
     'https://github.com/mgedmin/project-summary'),
    ('https://github.com/mgedmin/project-summary.git',
     'https://github.com/mgedmin/project-summary'),
    ('fridge:git/unrelated.git',
     'fridge:git/unrelated.git'),
])
def test_normalize_github_url(url, expected):
    assert normalize_github_url(url) == expected


def test_get_project_owner():
    result = get_project_owner('https://github.com/mgedmin/project-summary')
    assert result == 'mgedmin'


def test_get_project_name():
    result = get_project_name('https://github.com/mgedmin/project-summary')
    assert result == 'project-summary'


def git_commit(path, *args):
    subprocess.run([
        'git', '-c', 'user.name=nobody', '-c', 'user.email=nobody@localhost',
        'commit', '--allow-empty',
    ] + list(args), cwd=path)


def test_get_branch_name(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    git_commit(tmp_path, '-m', 'initial')
    result = get_branch_name(tmp_path)
    assert result == 'master'


def test_get_branch_name_detached_head(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    git_commit(tmp_path, '-m', 'initial')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=tmp_path,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', 'checkout', commit], cwd=tmp_path)
    result = get_branch_name(tmp_path)
    assert result == 'master'


def test_get_branch_name_detached_head_from_remote(tmp_path):
    origin = tmp_path / 'origin'
    subprocess.run(['git', 'init', origin])
    git_commit(origin, '-m', 'initial')
    checkout = tmp_path / 'checkout'
    subprocess.run(['git', 'clone', origin, checkout])
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=checkout,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', 'checkout', commit], cwd=checkout)
    result = get_branch_name(checkout)
    assert result == 'master'


def test_get_branch_name_detached_head_different_branch(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    git_commit(tmp_path, '-m', 'initial')
    subprocess.run(['git', 'checkout', '-b', 'feature'], cwd=tmp_path)
    git_commit(tmp_path, '-m', 'blabla')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=tmp_path,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', 'checkout', commit], cwd=tmp_path)
    result = get_branch_name(tmp_path)
    assert result == 'feature'


def test_get_branch_name_stale_detached_head(tmp_path):
    origin = tmp_path / 'origin'
    subprocess.run(['git', 'init', origin])
    git_commit(origin, '-m', 'initial')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=origin,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    git_commit(origin, '-m', 'blabla')
    checkout = tmp_path / 'checkout'
    subprocess.run(['git', 'clone', origin, checkout])
    subprocess.run(['git', 'checkout', commit], cwd=checkout)
    result = get_branch_name(checkout)
    assert result == 'master'


def test_get_branch_name_stale_detached_head_no_branch(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    git_commit(tmp_path, '-m', 'initial')
    git_commit(tmp_path, '-m', 'blabla')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=tmp_path,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', 'reset', '--hard', 'HEAD^'], cwd=tmp_path)
    subprocess.run(['git', 'checkout', commit], cwd=tmp_path)
    result = get_branch_name(tmp_path)
    assert result == '(detached)'


def test_get_branch_name_stale_detached_head_no_remote_branch(tmp_path):
    origin = tmp_path / 'origin'
    subprocess.run(['git', 'init', origin])
    git_commit(origin, '-m', 'initial')
    git_commit(origin, '-m', 'blabla')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=origin,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', 'reset', '--hard', 'HEAD^'], cwd=origin)
    checkout = tmp_path / 'checkout'
    subprocess.run(['git', 'clone', origin, checkout])
    subprocess.run(['git', 'checkout', commit], cwd=checkout)
    result = get_branch_name(checkout)
    assert result == '(detached)'


def test_get_last_tag(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    git_commit(tmp_path, '-m', 'initial')
    subprocess.run(['git', 'tag', '1.0'], cwd=tmp_path)
    result = get_last_tag(tmp_path)
    assert result == '1.0'


def test_get_date_of_tag(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    git_commit(tmp_path, '-m', 'initial')
    before = time.strftime('%Y-%m-%d %H:%M:%S %z')
    subprocess.run(['git', 'tag', '1.0'], cwd=tmp_path)
    after = time.strftime('%Y-%m-%d %H:%M:%S %z')
    result = get_date_of_tag(tmp_path, '1.0')
    assert before <= result <= after


def test_get_pending_commits(tmp_path):
    origin = tmp_path / 'origin'
    subprocess.run(['git', 'init', origin])
    git_commit(origin, '-m', 'initial')
    subprocess.run(['git', 'tag', '1.0'], cwd=origin)
    git_commit(origin, '-m', 'a')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=origin,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    checkout = tmp_path / 'checkout'
    subprocess.run(['git', 'clone', origin, checkout])
    result = get_pending_commits(checkout, '1.0')
    assert result == [f'{commit[:7]} a']


def test_get_supported_python_versions(tmp_path):
    setup_py = tmp_path / 'setup.py'
    setup_py.write_text(textwrap.dedent('''\
        from setuptools import setup
        setup(
            classifiers=[
                'Programming Language :: Python :: 3.8',
                'Programming Language :: Python :: 3.9',
            ],
        )
    '''))
    result = get_supported_python_versions(tmp_path)
    assert result == ['3.8', '3.9']


@pytest.fixture
def config():
    config = Configuration('/dev/null')
    return config


@pytest.fixture
def session(monkeypatch):
    session = MockSession()
    monkeypatch.setattr(requests, 'get', session.get)
    return session


@pytest.fixture
def project(tmp_path, config, session):
    project = Project(tmp_path, config, session)
    return project


def test_Project_repr(project):
    repr(project)


def test_Project_fetch(project):
    project.fetch()


def test_Project_pull(project):
    project.pull()


def test_Project_precompute(project):
    project.precompute(['url'])


def test_Project_url(project):
    assert project.url is None


@pytest.mark.parametrize("url, expected", [
    (None, False),
    ('https://git.example.com/example', False),
    ('https://github.com/mgedmin/example', True),
])
def test_Project_is_on_github(project, url, expected):
    project.url = url
    assert project.is_on_github == expected


@pytest.mark.parametrize("url", [
    None,
    'https://github.com/mgedmin/example',
])
def test_Project_uses_github_actions(project, url):
    project.url = url
    assert not project.uses_github_actions


@pytest.mark.parametrize("url", [
    None,
    'https://github.com/mgedmin/example',
])
def test_Project_uses_travis(project, url):
    project.url = url
    assert not project.uses_travis


@pytest.mark.parametrize("url", [
    None,
    'https://github.com/mgedmin/example',
])
def test_Project_uses_appveyor(project, config, url):
    config._config.set('project-summary', 'appveyor_account', 'mgedmin')
    project.url = url
    assert not project.uses_appveyor


def test_Project_uses_jenkins(project):
    assert not project.uses_jenkins


def test_Project_branch(project):
    project.branch


def test_Project_last_tag(project):
    project.last_tag


def test_Project_last_tag_date(project):
    project.last_tag_date


def test_Project_pending_commits(project):
    assert project.pending_commits == []


def test_Project_owner_unknown(project):
    assert not project.owner


def test_Project_owner_on_github(project):
    project.url = 'https://github.com/mgedmin/example'
    assert project.owner == 'mgedmin'


def test_Project_name_remote(project):
    project.url = 'https://github.com/mgedmin/example'
    assert project.name == 'example'


def test_Project_name_local(tmp_path, config, session):
    proj_path = tmp_path / "proj"
    proj_path.mkdir()
    project = Project(proj_path, config, session)
    assert project.name == 'proj'


def test_Project_pypi_name_local(project):
    project.name = 'proj'
    assert project.pypi_name == 'proj'


def test_Project_pypi_url(project):
    project.pypi_name = 'example'
    assert project.pypi_url == 'https://pypi.org/project/example/'


def test_Project_jenkins_job(tmp_path, config, session):
    proj_path = tmp_path / "proj"
    proj_path.mkdir()
    project = Project(proj_path, config, session)
    assert project.jenkins_job == 'proj'


def test_Project_jenkins_job_using_workspace(tmp_path, config, session):
    proj_path = tmp_path / "proj" / "workspace"
    proj_path.mkdir(parents=True)
    project = Project(proj_path, config, session)
    assert project.jenkins_job == 'proj'


def test_Project_compare_url_default(project):
    project.url = 'https://example.com/project'
    assert project.compare_url is None


def test_Project_compare_url_github(project):
    project.url = 'https://github.com/mgedmin/example'
    project.branch = 'main'
    project.last_tag = '1.0'
    assert project.compare_url == 'https://github.com/mgedmin/example/compare/1.0...main'


def test_Project_github_actions_urls_no_github_actions(project):
    assert project.github_actions_image_url is None
    assert project.github_actions_url is None


def test_Project_github_actions_urls_github(project):
    project.owner = 'mgedmin'
    project.name = 'example'
    project.branch = 'main'
    project.uses_github_actions = True
    assert project.github_actions_image_url == 'https://github.com/mgedmin/example/workflows/build/badge.svg?branch=main'
    assert project.github_actions_url == 'https://github.com/mgedmin/example/actions'


def test_Project_github_actions_status_no_github_actions(project):
    assert project.github_actions_status is None


def test_Project_github_actions_status_with_github_actions(project, session):
    session._prototype.update({
        'https://example.com/buildstatus.svg': MockResponse(
            text=GHA_STATUS_ICON_BUILD_PASSING,
        ),
    })
    project.uses_github_actions = True
    project.github_actions_image_url = 'https://example.com/buildstatus.svg'
    assert project.github_actions_status == 'passing'


def test_Project_travis_urls_no_travis(project):
    assert project.travis_image_url is None
    assert project.travis_url is None


def test_Project_travis_urls_github(project):
    project.owner = 'mgedmin'
    project.name = 'example'
    project.branch = 'main'
    project.uses_travis = True
    assert project.travis_image_url == 'https://api.travis-ci.com/mgedmin/example.svg?branch=main'
    assert project.travis_url == 'https://travis-ci.com/mgedmin/example'


def test_Project_travis_status_no_travis(project):
    assert project.travis_status is None


def test_Project_travis_status_with_travis(project, session):
    session._prototype.update({
        'https://example.com/buildstatus.svg': MockResponse(
            text=TRAVIS_STATUS_ICON_BUILD_PASSING,
        ),
    })
    project.uses_travis = True
    project.travis_image_url = 'https://example.com/buildstatus.svg'
    assert project.travis_status == 'passing'


def test_Project_parse_svg_text():
    result = Project._parse_svg_text('''
      <!-- this is not real svg actually -->
      <svg xmlns="http://www.w3.org/2000/svg">
      <text fill-opacity="0.5">shadow text</text>
      <text>hello</text>
      <text>cruel</text>
      <text><tspan>world</tspan></text>
      </svg>
    ''', {'cruel'})
    assert result == 'hello world'


def test_Project_parse_svg_text_no_exceptions_pls():
    result = Project._parse_svg_text('''
    <this is not valid svg!
    ''', {})
    assert result == ''


def test_Project_appveyor_urls_no_appveyor(project):
    assert project.appveyor_image_url is None
    assert project.appveyor_url is None


def test_Project_appveyor_urls_github(project, config):
    config._config.set('project-summary', 'appveyor_account', 'mgedmin')
    project.owner = 'mgedmin'
    project.name = 'example'
    project.branch = 'main'
    project.uses_appveyor = True
    assert project.appveyor_image_url == 'https://ci.appveyor.com/api/projects/status/github/mgedmin/example?branch=main&svg=true'
    assert project.appveyor_url == 'https://ci.appveyor.com/project/mgedmin/example/branch/main'


def test_Project_appveyor_status_no_appveyor(project):
    assert project.appveyor_status is None


def test_Project_appveyor_status_with_appveyor(project, session):
    session._prototype.update({
        'https://example.com/buildstatus.svg': MockResponse(
            text=APPVEYOR_STATUS_ICON_BUILD_PASSING,
        ),
    })
    project.uses_appveyor = True
    project.appveyor_image_url = 'https://example.com/buildstatus.svg'
    assert project.appveyor_status == 'passing'


def test_Project_coveralls_urls_no_coveralls(project):
    assert project.coveralls_image_url is None
    assert project.coveralls_url is None


def test_Project_coveralls_urls_github(project):
    project.owner = 'mgedmin'
    project.name = 'example'
    project.branch = 'main'
    project.uses_travis = True
    assert project.coveralls_image_url == 'https://coveralls.io/repos/mgedmin/example/badge.svg?branch=main'
    assert project.coveralls_url == 'https://coveralls.io/r/mgedmin/example?branch=main'


def test_Project_coverage_number_no_coveralls(project):
    assert project.coverage_number is None


def test_Project_coverage_number_coveralls(project, session):
    session._prototype.update({
        'https://example.com/coverage.svg': MockResponse(
            status_code=302,
            headers={
                'Location': 'https://s3.amazonaws.com/assets.coveralls.io/badges/coveralls_42.svg'
            },
        ),
    })
    project.coveralls_image_url = 'https://example.com/coverage.svg'
    assert project.coverage_number == 42


def test_Project_coverage_number_coverage_unknown(project, session):
    session._prototype.update({
        'https://example.com/coverage.svg': MockResponse(
            status_code=302,
            headers={
                'Location': 'https://s3.amazonaws.com/assets.coveralls.io/badges/coveralls_unknown.svg'
            },
        ),
    })
    project.coveralls_image_url = 'https://example.com/coverage.svg'
    assert project.coverage_number is None


def test_Project_coverage_number_coverage_unavailable(project, session):
    session._prototype.update({
        'https://example.com/coverage.svg': MockResponse(
            status_code=200,
        ),
    })
    project.coveralls_image_url = 'https://example.com/coverage.svg'
    assert project.coverage_number is None


def test_Project_coverage(project):
    project.coverage_number = 42
    assert project.coverage('{}%', 'n/a') == '42%'


def test_Project_coverage_unknown(project):
    project.coverage_number = None
    assert project.coverage('{}%', 'n/a') == 'n/a'


def test_Project_urls_no_jenkins(project):
    job = JenkinsJobConfig()
    assert project.get_jenkins_image_url(job) is None
    assert project.get_jenkins_url(job) is None
    assert project.get_jenkins_status(job) is None


def test_Project_urls_jenkins(project, config):
    config.jenkins_url = 'http://example.com'
    project.jenkins_job = 'project'
    job = JenkinsJobConfig('{name}-linux')
    assert project.get_jenkins_image_url(job) == 'http://example.com/job/project-linux/badge/icon'
    assert project.get_jenkins_url(job) == 'http://example.com/job/project-linux/'


def test_Project_get_jenkins_status(project, session, config):
    config.jenkins_url = 'http://example.com'
    project.jenkins_job = 'project'
    job = JenkinsJobConfig()
    session._prototype.update({
        'http://example.com/job/project/badge/icon': MockResponse(
            text=JENKINS_STATUS_ICON_BUILD_PASSING,
        ),
    })
    assert project.get_jenkins_status(job) == 'passing'


def test_Project_python_versions(project):
    assert project.python_versions == []


def test_Project_github_issues_and_pulls_no_github(project):
    assert project.github_issues_and_pulls == []


def test_Project_github_issues_and_pulls_github(project, session):
    session._prototype.update({
        'https://api.github.com/repos/mgedmin/project/issues?per_page=100': MockResponse(
            json=[{'an issue': 'yes very good'}],
        ),
    })
    project.is_on_github = True
    project.owner = 'mgedmin'
    project.name = 'project'
    assert project.github_issues_and_pulls == [
        {'an issue': 'yes very good'},
    ]


def test_Project_github_issues_and_github_pulls(project):
    project.github_issues_and_pulls = [
        {'issue': 'this'},
        {'pull_request': 'that'},
    ]
    assert project.github_issues == [{'issue': 'this'}]
    assert project.github_pulls == [{'pull_request': 'that'}]


def test_Project_open_issues_counts(project):
    project.github_issues = [
        {'issue': 'this', 'labels': []},
        {'issue': 'that', 'labels': [{'name': 'bug'}]},
    ]
    assert project.open_issues_count == 2
    assert project.unlabeled_open_issues_count == 1


def test_Project_issues_url_no_github(project):
    assert project.issues_url is None


def test_Project_issues_url_gitub(project):
    project.is_on_github = True
    project.url = 'https://github.com/mgedmin/example'
    assert project.issues_url == 'https://github.com/mgedmin/example/issues'


def test_Project_open_pulls_counts(project):
    project.github_pulls = [
        {'pull_request': 'this', 'labels': []},
        {'pull_request': 'that', 'labels': [{'name': 'bug'}]},
    ]
    assert project.open_pulls_count == 2
    assert project.unlabeled_open_pulls_count == 1


def test_Project_pulls_url_no_github(project):
    assert project.pulls_url is None


def test_Project_pulls_url_gitub(project):
    project.is_on_github = True
    project.url = 'https://github.com/mgedmin/example'
    assert project.pulls_url == 'https://github.com/mgedmin/example/pulls'


def test_Project_pypistats_url(project):
    project.pypi_name = 'example'
    assert project.pypistats_url == 'https://pypistats.org/packages/example'


def test_Project_downloads(project, tmp_path, monkeypatch, session):
    monkeypatch.setattr(pypistats, 'CACHE_DIR', tmp_path / 'pypistats-cache')
    session._prototype.update({
        'https://pypistats.org/api/packages/example/recent': MockResponse(
            json={
                'data': {
                    'last_month': 42,
                },
            },
        ),
        None: MockResponse(404),
    })
    project.pypi_name = 'example'
    assert project.downloads == 42


def test_Project_downloads_error(project, tmp_path, monkeypatch, session):
    monkeypatch.setattr(pypistats, 'CACHE_DIR', tmp_path / 'pypistats-cache')
    session._prototype.update({
        'https://pypistats.org/api/packages/example/recent': MockResponse(
            500,
        ),
        None: MockResponse(404),
    })
    project.pypi_name = 'example'
    assert project.downloads is None


def test_get_projects(tmp_path, config, session):
    proj = (tmp_path / 'a')
    subprocess.run(['git', 'init', proj])
    git_commit(proj, '-m', 'a')
    subprocess.run(['git', 'tag', '1.0'], cwd=proj)
    config._config.set('project-summary', 'projects', str(tmp_path / '*'))
    projects = get_projects(config, session)
    assert [p.name for p in projects] == ['a']


def test_filter_projects_can_skip_names(tmp_path, config, session):
    p1 = Project(tmp_path, config, session)
    p1.name = 'a'
    p1.last_tag = '0.1'
    p2 = Project(tmp_path, config, session)
    p2.name = 'b'
    p2.last_tag = '0.2'
    config.ignore = ['a']
    assert list(_filter_projects([p1, p2], config)) == [p2]


def test_filter_projects_can_skip_branches(tmp_path, config, session):
    p1 = Project(tmp_path, config, session)
    p1.branch = 'master'
    p1.last_tag = '0.1'
    p2 = Project(tmp_path, config, session)
    p2.branch = 'devel'
    p1.last_tag = '0.2'
    config.skip_branches = True
    assert list(_filter_projects([p1, p2], config)) == [p1]


def test_filter_projects_can_fetch(tmp_path, config, session):
    p1 = Project(tmp_path, config, session)
    config.fetch = True
    assert list(_filter_projects([p1], config)) == []


def test_filter_projects_can_pull(tmp_path, config, session):
    p1 = Project(tmp_path, config, session)
    config.pull = True
    assert list(_filter_projects([p1], config)) == []


def test_mako_error_handler():
    template = Template('''
      blah blah
      ${arg + 1}
    ''')
    with pytest.raises(TypeError) as ctx:
        template.render_unicode(arg='a')
    tb = ''.join(traceback.format_tb(ctx.tb))
    assert '${arg + 1}' in tb
    assert 'line 3 in render_body' in tb


def test_html():
    assert html(None, 'foo bar', class_='ignored') == 'foo bar'
    assert html(None, 'foo < bar') == 'foo &lt; bar'
    assert html('span', 'foo bar') == '<span>foo bar</span>'
    assert html('span', 'foo < bar') == '<span>foo &lt; bar</span>'
    assert html('span', 'foo', title="bar") == '<span title="bar">foo</span>'
    assert html('span', 'foo', title="b>r") == '<span title="b&gt;r">foo</span>'
    assert html('span', 'foo', title='b"r') == '<span title="b&#34;r">foo</span>'
    assert html('span', 'foo', class_="bar") == '<span class="bar">foo</span>'
    assert html('img', src="a.png") == '<img src="a.png">'
    assert html('img', None, src="a.png") == '<img src="a.png">'
    assert html('a', html('img', src="a.png"), href="/") == '<a href="/"><img src="a.png"></a>'
    assert isinstance(html('hello'), markupsafe.Markup)


def test_template_rendering_escapes():
    template = Template('${arg}')
    assert template.render_unicode(arg='<hello>') == '&lt;hello&gt;'


def test_template_rendering_accepts_markup():
    template = Template('${arg}')
    assert template.render_unicode(arg=html('hello')) == '<hello></hello>'


def test_template_rendering_accepts_numbers():
    template = Template('${arg}')
    assert template.render_unicode(arg=42) == '42'


def test_Column_stylesheet_rules():
    col = Column()
    page = Page('foo', [col])
    assert col.stylesheet_rules(page) == []


def test_Column_stylesheet_rules_with_alignment():
    col = Column(css_class='bork', align='right')
    page = Page('foo', [col])
    assert col.stylesheet_rules(page) == ['''\
      #foo th.bork,
      #foo td.bork { text-align: right; }
    '''.rstrip(' ')]


def test_Column_stylesheet_narrow():
    col = Column('Croak', css_class='frog')
    page = Page('foo', [col])
    assert col.stylesheet_rules(page, 'narrow') == ['''\
        #foo td.frog:before { content: "Croak: "; }
    '''.rstrip(' ')]


def test_Column_stylesheet_narrow_discrim():
    pages = Pages([
        Page('foo', [
            Column('Croak', css_class='frog'),
            Column('Ribbit', css_class='frog'),
        ]),
    ])
    assert pages.stylesheet('narrow') == '''\
        #foo td:nth-child(1):before { content: "Croak: "; }
        #foo td:nth-child(2):before { content: "Ribbit: "; }
    '''.rstrip(' ')


def test_StatusColumn_stylesheet_last():
    pages = Pages([Page('foo', [
        StatusColumn(css_class='bork'),
        StatusColumn(css_class='fish'),
    ])])
    assert pages.stylesheet() == '''\
      #foo th.bork,
      #foo td.bork { padding-right: 0; }
    '''.rstrip(' ')


def test_Pages_iteration():
    foo = Page('foo', [])
    bar = Page('bar', [])
    pages = Pages([foo, bar])
    assert list(pages) == [foo, bar]


def test_Pages_stylesheet():
    pages = Pages([
        Page('foo', [
            Column(css_class='bork', align='right'),
            Column(css_class='fish', align='right'),
        ]),
        Page('bar', [
            Column(css_class='bork', align='right'),
        ])
    ])
    assert pages.stylesheet() == '''\
      #foo th.bork,
      #foo td.bork { text-align: right; }
      #foo th.fish,
      #foo td.fish { text-align: right; }
      #bar th.bork,
      #bar td.bork { text-align: right; }
    '''.rstrip(' ')
    assert isinstance(pages.stylesheet(), markupsafe.Markup)


def test_Page_js_text_extractors_empty():
    page = Page('foo', [])
    assert page.js_text_extractors() == ''


def test_Page_js_text_extractors():
    page = Page('foo', [
        DateColumn(),
        Column(),
        IssuesColumn(),
    ])
    assert page.js_text_extractors() == '''
            0: sortTitleAttribute,  // ISO-8601 date in title
            2: sortIssues           // issue counts in data attributes
    '''.strip()


def test_Page_js_render_header_empty():
    page = Page('foo', [])
    assert page.js_render_header() == ''


def test_Page_js_render_header_disjoint_set():
    page = Page('foo', [
        Column(),
        Column(align='right'),
        Column(),
        Column(align='right'),
    ])
    assert page.js_render_header() == '''
          onRenderHeader: function(idx, config, table) {
            // move the sort indicator to the left for right-aligned columns
            if (idx == 1 || idx == 3) {
              var $this = $(this);
              $this.find('div').prepend($this.find('i'));
            }
          },
    '''.lstrip('\n').rstrip(' ')


def test_Page_js_render_header_last_n_columns():
    page = Page('foo', [
        Column(),
        Column(),
        Column(align='right'),
        Column(align='right'),
    ])
    assert page.js_render_header() == '''
          onRenderHeader: function(idx, config, table) {
            // move the sort indicator to the left for right-aligned columns
            if (idx >= 2) {
              var $this = $(this);
              $this.find('div').prepend($this.find('i'));
            }
          },
    '''.lstrip('\n').rstrip(' ')
    assert isinstance(page.js_render_header(), markupsafe.Markup)


def test_Column_js_text_extractor_no_sort_rule():
    column = Column()
    assert column.js_text_extractor(3, True) == ''


def test_Column_stylesheet_rules_empty():
    column = Column()
    page = Page('foo', [column])
    column.css_rules_test = None
    assert column.stylesheet_rules(page, 'test') == []


def test_Column_stylesheet_rules_no_class():
    column = Column()
    page = Page('foo', [column])
    column.css_rules_test = CSS('td${discrim} { color: red; }')
    assert column.stylesheet_rules(page, 'test') == [
        'td:nth-child(1) { color: red; }',
    ]


def test_Column_stylesheet_rules_class():
    column = Column(css_class='foo')
    page = Page('foo', [column])
    column.css_rules_test = CSS('td${discrim} { color: red; }')
    assert column.stylesheet_rules(page, 'test') == [
        'td.foo { color: red; }',
    ]


def test_Column_stylesheet_rules_class_clash():
    column = Column(css_class='foo')
    page = Page('foo', [column, Column(css_class='foo')])
    column.css_rules_test = CSS('td${discrim} { color: red; }')
    assert column.stylesheet_rules(page, 'test') == [
        'td:nth-child(1) { color: red; }',
    ]


def test_Column_stylesheet_rules_markup():
    column = Column('<hey>', css_class='foo')
    page = Page('foo', [column])
    column.css_rules_test = CSS('td${discrim}:before { content: "${column.title|h}"; }')
    rules = column.stylesheet_rules(page, 'test')
    assert rules == [
        'td.foo:before { content: "&lt;hey&gt;"; }',
    ]
    assert isinstance(rules[0], markupsafe.Markup)


def test_Column_col():
    column = Column()
    assert column.col() == '<col>'
    assert isinstance(column.col(), markupsafe.Markup)


def test_Column_col_with_width():
    column = Column(width='50%')
    assert column.col() == '<col width="50%">'
    assert isinstance(column.col(), markupsafe.Markup)


def test_Column_th():
    column = Column('A > B')
    assert column.th() == '<th>A &gt; B</th>'
    assert isinstance(column.th(), markupsafe.Markup)


def test_Column_th_class():
    column = Column('A', css_class='foo')
    assert column.th() == '<th class="foo">A</th>'
    assert isinstance(column.th(), markupsafe.Markup)


def test_Column_th_title():
    column = Column('A')
    column.title_tooltip = 'xy > zzy'
    assert column.th() == '<th title="xy &gt; zzy">A</th>'
    assert isinstance(column.th(), markupsafe.Markup)


class FakeProject:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_Column_td():
    project = FakeProject()
    column = Column()
    column.inner_html = lambda project: '-'
    assert column.td(project) == '<td>-</td>'
    assert isinstance(column.td(project), markupsafe.Markup)


def test_Column_td_class():
    project = FakeProject()
    column = Column(css_class='foo')
    column.inner_html = lambda project: '-'
    assert column.td(project) == '<td class="foo">-</td>'
    assert isinstance(column.td(project), markupsafe.Markup)


def test_Column_td_tooltip():
    project = FakeProject()
    column = Column()
    column.inner_html = lambda project: '-'
    column.tooltip = lambda project: 'hey > ho'
    assert column.td(project) == '<td title="hey &gt; ho">-</td>'
    assert isinstance(column.td(project), markupsafe.Markup)


def test_Column_td_data():
    project = FakeProject()
    column = Column()
    column.inner_html = lambda project: '-'
    column.get_data = lambda project: {'hey': '> ho'}
    assert column.td(project) == '<td data-hey="&gt; ho">-</td>'
    assert isinstance(column.td(project), markupsafe.Markup)


def test_Column_inner_html_is_abstract_method():
    project = FakeProject()
    column = Column()
    with pytest.raises(NotImplementedError):
        column.inner_html(project)


def test_NameColumn():
    project = FakeProject(
        name='Project', url='https://example.com', branch='master',
    )
    column = NameColumn()
    assert column.inner_html(project) == (
        '<a href="https://example.com">Project</a>'
    )
    assert isinstance(column.inner_html(project), markupsafe.Markup)


def test_NameColumn_branch():
    project = FakeProject(
        name='Project', url='https://example.com', branch='0.9.x',
    )
    column = NameColumn()
    assert column.inner_html(project) == (
        '<a href="https://example.com">Project</a> 0.9.x'
    )
    assert isinstance(column.inner_html(project), markupsafe.Markup)


def test_VersionColumn(monkeypatch):
    project = FakeProject(
        last_tag='v0.9.42', pypi_url='https://example.com/pypi/project',
    )
    column = VersionColumn()
    assert column.inner_html(project) == (
        '<a href="https://example.com/pypi/project">v0.9.42</a>'
    )
    assert isinstance(column.inner_html(project), markupsafe.Markup)


def test_DateColumn(monkeypatch):
    monkeypatch.setattr(summary, 'nice_date', lambda d: 'last Tuesday')
    project = FakeProject(
        last_tag_date='2020-05-30 11:15:25 +0300',
    )
    column = DateColumn()
    assert column.td(project) == (
        '<td class="date" title="2020-05-30 11:15:25 +0300">last Tuesday</td>'
    )


def test_ChangesColumn():
    project = FakeProject(
        pending_commits=['Post-release version bump'],
        compare_url='https://example.com/diff/v0.9.42..',
    )
    column = ChangesColumn()
    assert column.inner_html(project) == (
        '<a href="https://example.com/diff/v0.9.42..">1 commit</a>'
    )
    assert isinstance(column.inner_html(project), markupsafe.Markup)


def test_ChangesColumn_more_commits():
    project = FakeProject(
        pending_commits=[
            'Post-release version bump',
            'Fix CI',
        ],
        compare_url='https://example.com/diff/v0.9.42..',
    )
    column = ChangesColumn()
    assert column.inner_html(project) == (
        '<a href="https://example.com/diff/v0.9.42..">2 commits</a>'
    )
    assert isinstance(column.inner_html(project), markupsafe.Markup)


def test_StatusColumn():
    project = FakeProject()
    column = StatusColumn()
    column.get_status = lambda project: ('/status', '/status.svg', 'unknown')
    assert column.inner_html(project) == (
        '<a href="/status"><img src="/status.svg" alt="unknown" height="20"></a>'
    )
    assert isinstance(column.inner_html(project), markupsafe.Markup)


def test_StatusColumn_not_available():
    project = FakeProject()
    column = StatusColumn()
    column.get_status = lambda project: (None, None, None)
    assert column.inner_html(project) == (
        '-'
    )


def test_StatusColumn_get_status_is_an_abstract_method():
    project = FakeProject()
    column = StatusColumn()
    with pytest.raises(NotImplementedError):
        column.get_status(project)


def test_BuildStatusColumn_get_status_gha():
    project = FakeProject(
        uses_github_actions=True,
        uses_travis=False,
        github_actions_url='/status',
        github_actions_image_url='/status.svg',
        github_actions_status='unknown',
    )
    column = BuildStatusColumn()
    assert column.get_status(project) == ('/status', '/status.svg', 'unknown')


def test_BuildStatusColumn_get_status_travis():
    project = FakeProject(
        uses_github_actions=False,
        uses_travis=True,
        travis_url='/status',
        travis_image_url='/status.svg',
        travis_status='unknown',
    )
    column = BuildStatusColumn()
    assert column.get_status(project) == ('/status', '/status.svg', 'unknown')


def test_GitHubActionsColumn_get_status():
    project = FakeProject(
        github_actions_url='/status',
        github_actions_image_url='/status.svg',
        github_actions_status='unknown',
    )
    column = GitHubActionsColumn()
    assert column.get_status(project) == ('/status', '/status.svg', 'unknown')


def test_TravisColumn_get_status():
    project = FakeProject(
        travis_url='/status',
        travis_image_url='/status.svg',
        travis_status='unknown',
    )
    column = TravisColumn()
    assert column.get_status(project) == ('/status', '/status.svg', 'unknown')


def test_JenkinsColumn():
    project = FakeProject(
        get_jenkins_url=lambda job: '/status',
        get_jenkins_image_url=lambda job: '/status.svg',
        get_jenkins_status=lambda job: 'unknown',
    )
    column = JenkinsColumn(JenkinsJobConfig())
    # Multiple spaces are ugly but HTML collapses them into one space, so I don't really care
    assert ' '.join(column.title_narrow.split()) == 'Jenkins status'
    assert column.get_status(project) == ('/status', '/status.svg', 'unknown')


def test_JenkinsColumn_with_title():
    column = JenkinsColumn(JenkinsJobConfig('{name}', 'Linux'))
    assert column.title_narrow == 'Jenkins Linux status'


def test_AppveyorColumn():
    project = FakeProject(
        appveyor_url='/status',
        appveyor_image_url='/status.svg',
        appveyor_status='unknown',
    )
    column = AppveyorColumn()
    assert column.get_status(project) == ('/status', '/status.svg', 'unknown')


def test_CoverallsColumn():
    project = FakeProject(
        coveralls_url='/coverage',
        coveralls_image_url='/coverage.svg',
        coverage=lambda fmt='{}', unknown='?': fmt.format(90),
    )
    column = CoverallsColumn()
    assert column.get_status(project) == ('/coverage', '/coverage.svg', '90%')
    assert column.get_data(project) == dict(coverage='90')


def test_DataColumn_stylesheet():
    col = DataColumn(css_class='bork')
    page = Page('foo', [col])
    assert col.stylesheet_rules(page) == ['''\
      #foo span.new { font-weight: bold; }
      #foo span.none { color: #999; }
    '''.rstrip(' ')]


def test_DataColumn_stylesheet_with_alignment():
    col = DataColumn(css_class='bork', align='right')
    page = Page('foo', [col])
    assert col.stylesheet_rules(page) == ['''\
      #foo th.bork,
      #foo td.bork { text-align: right; }
    '''.rstrip(' '), '''\
      #foo span.new { font-weight: bold; }
      #foo span.none { color: #999; }
    '''.rstrip(' ')]


def test_DataColumn_get_data():
    project = FakeProject()
    column = DataColumn()
    column.get_counts = lambda project: (1, 3)
    assert column.get_data(project) == dict(new='1', total='3')


def test_DataColumn_inner_html():
    project = FakeProject()
    column = DataColumn()
    column.get_counts = lambda project: (1, 3)
    column.get_url = lambda project: '/bugs'
    assert column.inner_html(project) == (
        '<a href="/bugs" title="1 new, 3 total"><span class="new">1</span> (3)</a>'
    )


def test_DataColumn_inner_html_no_bugs_at_all():
    project = FakeProject()
    column = DataColumn()
    column.get_counts = lambda project: (0, 0)
    column.get_url = lambda project: '/bugs'
    assert column.inner_html(project) == (
        '<a href="/bugs" title="0 new, 0 total">'
        '<span class="none">0</span> <span class="none">(0)</span>'
        '</a>'
    )


def test_DataColumn_get_counts_is_an_abstract_method():
    project = FakeProject()
    column = DataColumn()
    with pytest.raises(NotImplementedError):
        column.get_counts(project)


def test_DataColumn_get_url_is_an_abstract_method():
    project = FakeProject()
    column = DataColumn()
    with pytest.raises(NotImplementedError):
        column.get_url(project)


def test_IssuesColumn():
    project = FakeProject(
        unlabeled_open_issues_count=1,
        open_issues_count=3,
        issues_url='/issues',
    )
    column = IssuesColumn()
    assert column.get_url(project) == '/issues'
    assert column.get_counts(project) == (1, 3)


def test_PullsColumn():
    project = FakeProject(
        unlabeled_open_pulls_count=1,
        open_pulls_count=3,
        pulls_url='/pulls',
    )
    column = PullsColumn()
    assert column.get_url(project) == '/pulls'
    assert column.get_counts(project) == (1, 3)


def test_PythonSupportColumn():
    column = PythonSupportColumn('3.6')
    assert column.title_narrow == 'Python 3.6'
    assert column.title_tooltip == 'Supported until 2021-12-23'


def test_PythonSupportColumn_PyPy():
    column = PythonSupportColumn('PyPy')
    assert column.title_narrow == 'PyPy'
    assert column.title_tooltip is None


def test_PythonSupportColumn_yes():
    project = FakeProject(
        python_versions={'3.6', '3.7'},
    )
    column = PythonSupportColumn('3.6')
    assert isinstance(column.inner_html(project), markupsafe.Markup)


def test_PythonSupportColumn_no():
    project = FakeProject(
        python_versions={'3.6', '3.7'},
    )
    column = PythonSupportColumn('3.5')
    assert column.inner_html(project) == (
        '<span class="no">\u2212</span>'
    )
    assert isinstance(column.inner_html(project), markupsafe.Markup)


def test_PypiStatsColumn():
    project = FakeProject(
        pypistats_url='/stats',
        downloads=12345,
    )
    column = PypiStatsColumn()
    assert column.inner_html(project) == (
        '<a href="/stats">12,345</a>'
    )
    assert isinstance(column.inner_html(project), markupsafe.Markup)


def test_get_report_pages():
    config = Configuration('/dev/null')
    pages = get_report_pages(config)
    assert [page.title for page in pages] == [
        'Release status',
        'Maintenance',
        'Python versions',
    ]


def test_nice_date():
    nice_date("2019-06-06 17:43:14 +0300")  # should not raise


def test_pluralize():
    assert pluralize(1, 'issues') == '1 issue'
    assert pluralize(2, 'issues') == '2 issues'


def test_main_help(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['summary', '--help'])
    with pytest.raises(SystemExit):
        summary.main()


def test_main(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', [
        'summary',
    ])
    summary.main()


def test_main_html(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', [
        'summary', '--html', '-v', '--symlink-assets',
    ])
    summary.main()


def test_main_warn_output_file_ignored(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', [
        'summary', '-o', 'output.txt',
    ])
    summary.main()
    assert '--output-file ignored' in capsys.readouterr().out


def _raise(exc):
    def fn(*a, **kw):
        raise exc
    return fn


@pytest.mark.parametrize("exc", [
    ConnectionError,
    HTTPError,
    GitHubError,
])
def test_main_network_errors_produce_no_traceback(tmp_path, monkeypatch, capsys, exc):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', [
        'summary', '--html',
    ])
    monkeypatch.setattr(summary, 'print_html_report', _raise(exc))
    with pytest.raises(SystemExit):
        summary.main()
    out, err = capsys.readouterr()
    assert 'Traceback' not in out
    assert 'Traceback' not in err


def test_main_intenral_errors_produce_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', [
        'summary', '--html',
    ])
    monkeypatch.setattr(summary, 'print_html_report', _raise(Exception))
    with pytest.raises(SystemExit):
        summary.main()
    out, err = capsys.readouterr()
    assert 'Traceback' in err


def test_print_report(project):
    project.last_tag = '0.1'
    project.last_tag_date = '2020-05-30 11:15:25 +0300'
    print_report([project], verbose=2)


def test_print_html_report(tmp_path, config):
    projects = []
    print_html_report(projects, config, tmp_path / 'output.html')


def test_symlink_assets(tmp_path):
    symlink_assets(tmp_path / 'output.html')
    assert (tmp_path / 'assets' / 'css' / 'bootstrap.css').exists()
