import datetime
import json
import logging
import subprocess
import sys
import textwrap
import time

import markupsafe
import pytest
import requests
import requests_cache

import summary
from summary import (
    AppveyorColumn,
    CSS,
    ChangesColumn,
    Column,
    Configuration,
    CoverallsColumn,
    DataColumn,
    DateColumn,
    GitHubError,
    GitHubRateLimitError,
    IssuesColumn,
    JenkinsColumn,
    JenkinsJobConfig,
    NameColumn,
    Page,
    Pages,
    PullsColumn,
    PypiStatsColumn,
    PythonSupportColumn,
    StatusColumn,
    Template,
    TravisColumn,
    VersionColumn,
    format_cmd,
    get_branch_name,
    get_date_of_tag,
    get_last_tag,
    get_pending_commits,
    get_project_name,
    get_project_owner,
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
    reify,
    to_seconds,
)


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
    session.cache.save_response(cache_key, response)


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
    caplog.set_level(logging.DEBUG)
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

    def get(self, url):
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


def test_get_repos(tmp_path):
    (tmp_path / 'a' / '.git').mkdir(parents=True)
    config = Configuration(tmp_path / 'ps.cfg')
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


def test_get_branch_name(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=tmp_path)
    result = get_branch_name(tmp_path)
    assert result == 'master'


def test_get_branch_name_detached_head(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=tmp_path)
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=tmp_path,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', 'checkout', commit], cwd=tmp_path)
    result = get_branch_name(tmp_path)
    assert result == 'master'


def test_get_branch_name_detached_head_from_remote(tmp_path):
    origin = tmp_path / 'origin'
    subprocess.run(['git', 'init', origin])
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=origin)
    checkout = tmp_path / 'checkout'
    subprocess.run(['git', 'clone', origin, checkout])
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=checkout,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', 'checkout', commit], cwd=checkout)
    result = get_branch_name(checkout)
    assert result == 'master'


def test_get_branch_name_detached_head_different_branch(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=tmp_path)
    subprocess.run(['git', 'checkout', '-b', 'feature'], cwd=tmp_path)
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'blabla'], cwd=tmp_path)
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=tmp_path,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', 'checkout', commit], cwd=tmp_path)
    result = get_branch_name(tmp_path)
    assert result == 'feature'


def test_get_branch_name_stale_detached_head(tmp_path):
    origin = tmp_path / 'origin'
    subprocess.run(['git', 'init', origin])
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=origin)
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=origin,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'blabla'], cwd=origin)
    checkout = tmp_path / 'checkout'
    subprocess.run(['git', 'clone', origin, checkout])
    subprocess.run(['git', 'checkout', commit], cwd=checkout)
    result = get_branch_name(checkout)
    assert result == 'master'


def test_get_branch_name_stale_detached_head_no_branch(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=tmp_path)
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'blabla'], cwd=tmp_path)
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=tmp_path,
                            stdout=subprocess.PIPE).stdout.decode().strip()
    subprocess.run(['git', 'reset', '--hard', 'HEAD^'], cwd=tmp_path)
    subprocess.run(['git', 'checkout', commit], cwd=tmp_path)
    result = get_branch_name(tmp_path)
    assert result == '(detached)'


def test_get_branch_name_stale_detached_head_no_remote_branch(tmp_path):
    origin = tmp_path / 'origin'
    subprocess.run(['git', 'init', origin])
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=origin)
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'blabla'], cwd=origin)
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
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=tmp_path)
    subprocess.run(['git', 'tag', '1.0'], cwd=tmp_path)
    result = get_last_tag(tmp_path)
    assert result == '1.0'


def test_get_date_of_tag(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path)
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=tmp_path)
    subprocess.run(['git', 'tag', '1.0'], cwd=tmp_path)
    before = time.strftime('%Y-%m-%d %H:%M:%S %z')
    result = get_date_of_tag(tmp_path, '1.0')
    after = time.strftime('%Y-%m-%d %H:%M:%S %z')
    assert before <= result <= after


def test_get_pending_commits(tmp_path):
    origin = tmp_path / 'origin'
    subprocess.run(['git', 'init', origin])
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'initial'], cwd=origin)
    subprocess.run(['git', 'tag', '1.0'], cwd=origin)
    subprocess.run(['git', '-c', 'user.email=nobody@localhost', 'commit', '--allow-empty',
                    '-m', 'a'], cwd=origin)
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
