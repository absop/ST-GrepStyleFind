import re

import sublime
import sublime_plugin

from collections import namedtuple


Header = namedtuple('Header', ['stat', 'jump_point', 'emph_region'])


def summarize_regions_with_context(view, regions, header=None):
    if Settings.unique_line:
        summarize_unique_row(view, regions, header)
    else:
        summarize_one_match_per_row(view, regions, header)

def summarize_one_match_per_row(view, regions, header):
    results = []
    max_row = 0
    max_col = 0
    max_line_length = Settings.max_line_length
    for region in regions:
        row, col = view.rowcol(region.a)
        row += 1
        col += 1
        line = view.line(region)
        if line.size() > max_line_length:
            pass
        results.append((row, col, region, line))
        if row > max_row:
            max_row = row
        if col > max_col:
            max_col = col
    Region = sublime.Region
    wr = len(str(max_row))
    wc = len(str(max_col))
    col_offset = wr + 1 + wc + 2
    highlight_regions = []
    if header is not None:
        stat = header.stat
        highlight_regions.append(header.emph_region)
        header_jump_point = header.jump_point
    else:
        header_jump_point = None
        count = len(results)
        plurar = 's' if count > 1 else ''
        stat = f'{count} selection{plurar}\n'
    offset = len(stat)
    result_lines = [stat]
    for row, col, region, line in results:
        linetext = view.substr(line)
        stripped = linetext.lstrip()
        indenter = len(linetext) - len(stripped)
        stripped = stripped.rstrip()
        # TODO: stripped should contain the matched word
        if len(stripped) > max_line_length:
            stripped = stripped[:max_line_length-3] + '...'
        line_with_rowcol = f'{row:>{wr}}:{col:<{wc}}   {stripped}'
        result_lines.append(line_with_rowcol)
        offset += 1
        begin = offset + col_offset + col - indenter
        offset += len(line_with_rowcol)
        end = begin + region.size()
        if end > offset:
            end = offset
        highlight_regions.append(Region(begin, end))
    result_text = '\n'.join(result_lines)

    create_summary_panel(
        view,
        result_text,
        highlight_regions,
        header_jump_point
        )


def summarize_unique_row(view, regions, header):
    last_row = 0
    line_regions = []    # [(row, line, [(col, size)])]
    for region in regions:
        a, b = region.a, region.b
        row, col = view.rowcol(a)
        row += 1
        col += 1
        if row == last_row:
            line_regions[-1][2].append((col, b - a, a, b))
        else:
            last_row = row
            line = view.line(region)
            line_regions.append((row, line, [(col, b - a, a, b)]))

    Region = sublime.Region
    row_width = len(str(last_row))
    indent_size = row_width + 3
    highlight_regions = []
    region_jump_point = []
    if header is not None:
        stat = header.stat
        highlight_regions.append(header.emph_region)
        r = header.jump_point
        if r is not None:
            region_jump_point.append([0, len(stat) - 1, r.a, r.b])
    else:
        count = len(regions)
        plurar = 's' if count > 1 else ''
        stat = f'{count} selection{plurar}\n'
    start_point = len(stat)
    result_lines = [stat]
    if Settings.keep_indent:
        for row, line, spans in line_regions:
            linetext = view.substr(line)
            line_with_row = f'{row:>{row_width}}   {linetext}'
            result_lines.append(line_with_row)
            start = start_point + 1
            for col, size, a, b in spans:
                begin = start_point + indent_size + col
                end = begin + size
                highlight_regions.append(Region(begin, end))
                end += 1
                region_jump_point.append([start, end, a, b])
                start = end
            start_point += len(line_with_row) + 1  # '\n'.join
            region_jump_point[-1][1] = start_point
    else:
        for row, line, spans in line_regions:
            linetext = view.substr(line)
            stripped = linetext.lstrip()
            indent_n = len(linetext) - len(stripped)
            stripped = stripped.rstrip()
            line_with_row = f'{row:>{row_width}}   {stripped}'
            result_lines.append(line_with_row)
            start = start_point + 1
            for col, size, a, b in spans:
                begin = start_point + indent_size + col - indent_n
                end = begin + size
                highlight_regions.append(Region(begin, end))
                end += 1
                region_jump_point.append([start, end, a, b])
                start = end
            start_point += len(line_with_row) + 1  # '\n'.join
            region_jump_point[-1][1] = start_point
    result_text = '\n'.join(result_lines)

    create_summary_panel(
        view,
        result_text,
        highlight_regions,
        region_jump_point
        )


def create_summary_panel(view, text, regions, region_jump_point):
    window = view.window()
    panel = window.create_output_panel('LineFinder')
    panel.assign_syntax('LineFinder.sublime-syntax')
    panel.settings().update(Settings.panel_settings)
    panel.settings()['master_view.region_jump_point'] = region_jump_point
    panel.settings()['master_view.id'] = view.id()
    panel.set_read_only(False)
    panel.run_command('append', {'characters': text})
    panel.set_read_only(True)
    panel.add_regions('__LineFinder__.match', regions,
        scope=Settings.color,
        flags=sublime.DRAW_OUTLINED
        )
    window.run_command('show_panel', {'panel': 'output.LineFinder'})


class LineFinder(sublime_plugin.TextCommand):
    def find_all(self, pattern):
        if FindOption.whole_word:
            if not FindOption.regex:
                pattern = re.escape(pattern)
            pattern = rf'\b{pattern}\b'
        return self.view.find_all(pattern, FindOption.flags)

    def grep(self, pattern, position=None):
        regions = self.find_all(pattern)
        count = len(regions)
        plurar = 'es' if count > 1 else ''
        stat = f"{count} match{plurar} of '"
        begin = len(stat)
        stat += pattern
        end = len(stat)
        options = FindOption.checked_options
        if options:
            stat += f"' {options}\n"
        else:
            stat += f"'\n"
        header = Header(stat, position, sublime.Region(begin, end))
        summarize_regions_with_context(self.view, regions, header)

    def get_selection(self):
        view = self.view
        selections = view.sel()
        self.pattern = None
        self.selection = None
        if selections:
            region = selections[0]
            if not region.empty():
                if region.size() < Settings.max_line_length:
                    row_a = view.rowcol(region.a)[0]
                    row_b = view.rowcol(region.b)[0]
                    if row_a != row_b:
                        return
                    if content := view.substr(region).strip():
                        self.selection = view.find(content, region.begin(),
                            flags=sublime.FindFlags.LITERAL
                            )
                        self.pattern = content
            elif Settings.auto_select:
                region = view.word(region)
                if 0 < region.size() < Settings.max_line_length:
                    word = view.substr(region).strip(Settings.word_separators)
                    if len(word) > 0:
                        self.selection = view.find(word, region.begin(),
                            flags=sublime.FindFlags.LITERAL
                            )
                        self.pattern = word
        return self.pattern


class LineFinderFindSelectionCommand(LineFinder):
    pattern = None

    def is_enabled(self):
        if self.view.element() is None:
            return self.get_selection() is not None
        return False

    def run(self, edit):
        if self.pattern is None:
            if self.get_selection() is None:
                return
        self.grep(self.pattern, self.selection)


class PatternInputHandler(sublime_plugin.TextInputHandler):
    regions_key = '__LineFinder__.input'

    def __init__(self, caller, initial_text=None):
        self.caller = caller
        self.view = caller.view
        self.regions = None
        self.add_regions = self.view.add_regions
        self.erase_regions = self.view.erase_regions
        self._initial_text = initial_text
        self.refresher = LineFinderPreviewInputCommand

    def placeholder(self):
        return '<pattern>'

    def initial_text(self):
        return self._initial_text or self.caller.get_selection() or ''

    def validate(self, pattern):
        return bool(self.regions)

    def confirm(self, pattern):
        self.refresher.inputed_text = None
        self.erase_regions(self.regions_key)

    def cancel(self):
        self.refresher.inputed_text = None
        self.erase_regions(self.regions_key)

    def preview(self, pattern):
        self.refresher.inputed_text = pattern
        if pattern:
            self.regions = self.caller.find_all(pattern)
        else:
            self.regions = None
        self.erase_regions(self.regions_key)
        if self.regions:
            self.add_regions(
                self.regions_key,
                self.regions,
                scope=Settings.color,
                flags=sublime.DRAW_OUTLINED
                )
            self.show_regions(self.regions)
        stat = ''
        if self.regions is not None:
            count = len(self.regions)
            if count == 0:
                stat = f'Not found'
            elif count == 1:
                stat = f'{count} match'
            else:
                stat = f'{count} matches'
        return sublime.Html(
f"""\
<body>
<style>
{FindOption.preview_css}
hr {{
    display: block;
    height: 1px;
    border: 0;
    border-top: 1px solid #ccc;
    margin: 0.5em 0;
    padding: 0;
}}
</style>
<dev id=options>
{FindOption.preview_html}
</dev>
<hr>
<dev id=stat>
{stat}
</dev>
</body>
""")

    def show_regions(self, regions):
        visible_region = self.view.visible_region()
        begin = visible_region.a
        end = visible_region.b
        lo, hi = 0, len(regions) - 1
        while lo <= hi:
            mi = (lo + hi) >> 1
            re = regions[mi]
            if begin >= re.b:
                lo = mi + 1
            elif end <= re.a:
                hi = mi - 1
            else:
                break
        if not visible_region.contains(re):
            self.view.show_at_center(re)


class LineFinderFindInputCommand(LineFinder):
    def run(self, edit, pattern, inputed_text=None):
        self.grep(pattern)

    def input(self, args):
        return PatternInputHandler(self, initial_text=args.get('inputed_text'))


class LineFinderPreviewInputCommand(sublime_plugin.TextCommand):
    inputed_text = None

    def run(self, edit, option=None):
        if option:
            Settings.toggle_find_option(option)
        inputed_text = self.inputed_text
        window = self.view.window()
        window.run_command('hide_overlay')
        window.run_command(
            'show_overlay',
            {
                'overlay': 'command_palette',
                'command': 'line_finder_find_input',
                'args': {
                    'inputed_text': inputed_text
                }
            }
        )


class LineFinderSummarizeSelectionsCommand(sublime_plugin.TextCommand):
    def is_enabled(self):
        return self.view.has_non_empty_selection_region()

    def run(self, edit):
        summarize_regions_with_context(
            self.view,
            self.view.sel(),
            )


class LineFinderGotoMatchCommand(sublime_plugin.TextCommand):
    regions_key = '__LineFinder__.goto'
    highlight_token = 0

    def run_(self, edit_token, args):
        fallback = False
        settings = self.view.settings()
        element = self.view.element()
        if element != 'output:output':
            fallback = True
        else:
            syntax = settings.get('syntax')
            if syntax != 'LineFinder.sublime-syntax':
                fallback = True
        if fallback:
            fallback_command = args.get('command')
            if fallback_command:
                new_args = dict({'event': args['event']}.items())
                new_args.update(dict(args['args'].items()))
                self.view.run_command(fallback_command, new_args)
            return
        master_view = sublime.View(settings.get('master_view.id'))
        if not master_view.is_valid():
            sublime.status_message('The master view has changed')
            return
        region_jump_point = settings.get('master_view.region_jump_point')
        event = args['event']
        point = self.view.window_to_text((event['x'], event['y']))
        region = self.search_jump_point(region_jump_point, point)
        if not region:
            return

        def clear_region(token):
            if token > 0 and token == cls.highlight_token:
                master_view.erase_regions(cls.regions_key)

        cls = self.__class__
        clear_region(cls.highlight_token)
        cls.highlight_token += 1

        a, b = region
        region = sublime.Region(a, b)
        if not master_view.visible_region().contains(region):
            master_view.show_at_center(a)
        master_view.sel().clear()
        master_view.sel().add(a)
        master_view.add_regions(
            self.regions_key,
            [region],
            scope=Settings.color,
            flags=sublime.DRAW_OUTLINED
            )
        sublime.set_timeout(
            (lambda token:
                lambda: clear_region(token)
                )(cls.highlight_token),
            3000)
        self.view.window().focus_view(master_view)

    def search_jump_point(self, region_jump_point, point):
        row = 0
        lo, hi = 0, len(region_jump_point) - 1
        while lo <= hi:
            mi = (lo + hi) >> 1
            a, b, target_a, target_b = region_jump_point[mi]
            if point > b:
                lo = mi + 1
            elif point < a:
                hi = mi - 1
            else:
                return target_a, target_b


class LineFinderToggleOptionCommand(sublime_plugin.ApplicationCommand):
    def run(self, option):
        Settings.toggle_find_option(option)

    def is_checked(self, option):
        return Settings.storage.get('find_options', {}).get(option, False)


class FindOption:
    flags           : int
    regex           : bool
    case_sensitive  : bool
    whole_word      : bool
    checked_options : str
    preview_html    : str
    preview_css     : str = """\
#options {
    display: block;
}
span.checkbox {
    font-family: monospace;
}
a {
    text-decoration: none;
}
a.checked, span.checked {
    color: var(--accent);
}
a.unchecked {
    color: color(gray alpha(0.25));
}"""

    @classmethod
    def make_option_checkbox(cls, option, checked, description):
        url = sublime.command_url(
            'line_finder_preview_input', args={'option': option}
        )
        if checked:
            status = 'checked'
        else:
            status = 'unchecked'
        return (
            f'<dev>'
            f'<span class="checkbox">'
            f'[<a href="{url}" class="{status}">√</a>] '
            f'</span>'
            f'<span class="{status}">{description}</span>'
            f'</dev>'
        )

    @classmethod
    def update(cls, options):

        cls.regex = options.get('regex', False)
        cls.case_sensitive = options.get('case_sensitive', False)
        cls.whole_word = options.get('whole_word', False)

        flags = 0
        checked = []
        if cls.regex:
            checked.append('regex')
        else:
            flags |= sublime.FindFlags.LITERAL
        if cls.case_sensitive:
            checked.append('case sensitive')
        else:
            flags |= sublime.FindFlags.IGNORECASE
        if cls.whole_word:
            checked.append('whole word')
            if flags & sublime.FindFlags.LITERAL:
                flags ^= sublime.FindFlags.LITERAL

        cls.flags = flags
        cls.checked_options = f'({", ".join(checked)})' if checked else ''
        cls.preview_html = '<br>\n'.join(
            cls.make_option_checkbox(key, options.get(key, False), description)
            for key, description in {
                'regex': 'Regular expression',
                'case_sensitive': 'Case sensitive',
                'whole_word': 'Whole word'
            }.items()
        )


class Settings:
    FILE_NAME = 'LineFinder.sublime-settings'

    @classmethod
    def load(cls):
        cls.color = cls.storage.get('color', 'region.purplish')
        cls.panel_settings = cls.storage.get('output_panel.settings', {})
        cls.auto_select = cls.storage.get('auto_select', True)
        cls.word_separators = cls.storage.get('word_separators', '')
        cls.max_line_length = cls.storage.get('max_line_length', 100)
        cls.keep_indent = cls.storage.get('output_panel.keep_indent', False)
        cls.unique_line = cls.storage.get('output_panel.unique_line', True)
        FindOption.update(cls.storage.get('find_options', {}))

    @classmethod
    def toggle_find_option(cls, option):
        options = cls.storage.get('find_options', {})
        options[option] = not options.get(option)
        cls.storage.set('find_options', options)
        cls.save()

    @classmethod
    def save(cls):
        sublime.save_settings(cls.FILE_NAME)

    @classmethod
    def reload(cls):
        cls.storage = sublime.load_settings(cls.FILE_NAME)
        cls.storage.add_on_change('__LineFinder__', cls.load)
        cls.load()

    @classmethod
    def unload(cls):
        cls.storage.clear_on_change('__LineFinder__')


def plugin_loaded():
    sublime.set_timeout_async(Settings.reload)


def plugin_unloaded():
    Settings.unload()
