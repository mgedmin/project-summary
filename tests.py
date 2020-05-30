import subprocess
import textwrap

import markupsafe
import pytest

from summary import (
    Column,
    Configuration,
    DataColumn,
    DateColumn,
    IssuesColumn,
    JenkinsJobConfig,
    Page,
    Pages,
    StatusColumn,
    Template,
    format_cmd,
    get_project_name,
    get_project_owner,
    html,
    nice_date,
    normalize_github_url,
    pipe,
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


def test_nice_date():
    nice_date("2019-06-06 17:43:14 +0300")  # should not raise


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
