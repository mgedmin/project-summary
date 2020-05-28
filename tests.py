import markupsafe
import pytest

from summary import (
    Column,
    DataColumn,
    Page,
    Pages,
    StatusColumn,
    Template,
    format_cmd,
    html,
    nice_date,
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
