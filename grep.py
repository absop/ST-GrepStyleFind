import re

import sublime
import sublime_plugin

from collections import namedtuple


Header = namedtuple('Header', ['stat', 'jump_point', 'emph_region'])


def summarize_regions_with_context(view, regions, header=None):
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


def create_summary_panel(view, text, regions, header_jump_point):
    window = view.window()
    panel = window.create_output_panel('GrepStyleFind')
    panel.assign_syntax('GrepStyleFind.sublime-syntax')
    panel.settings().update(Settings.panel_settings)
    panel.settings()['main_view.header_jump_point'] = header_jump_point
    panel.settings()['main_view.id'] = view.id()
    panel.set_read_only(False)
    panel.run_command('append', {'characters': text})
    panel.set_read_only(True)
    panel.add_regions('*grep*', regions,
        scope=Settings.color,
        flags=sublime.DRAW_OUTLINED
        )
    window.run_command('show_panel', {'panel': 'output.GrepStyleFind'})


class GrepFinder(sublime_plugin.TextCommand):
    def find_all(self, pattern):
        find_options = Settings.storage.get('find_options', {})
        case_sensitive = find_options.get('case_sensitive', False)
        regexp = find_options.get('regexp', False)
        whole_word = find_options.get('whole_word', False)

        flags = 0
        options = []
        if regexp:
            options.append('regex')
        else:
            flags |= sublime.FindFlags.LITERAL
        if case_sensitive:
            options.append('case sensitive')
        else:
            flags |= sublime.FindFlags.IGNORECASE
        if whole_word:
            options.append('whole word')
            if flags & sublime.FindFlags.LITERAL:
                flags ^= sublime.FindFlags.LITERAL
                pattern = re.escape(pattern)
            pattern = rf'\b{pattern}\b'

        return options, self.view.find_all(pattern, flags)

    def grep(self, pattern, position=None):
        options, regions = self.find_all(pattern)
        count = len(regions)
        plurar = 'es' if count > 1 else ''
        stat = f"{count} match{plurar} of '"
        begin = len(stat)
        stat += pattern
        end = len(stat)
        if options:
            stat += f"' ({', '.join(options)})\n"
        else:
            stat += f"'\n"
        header = Header(stat, position, sublime.Region(begin, end))
        summarize_regions_with_context(self.view, regions, header)


class GrepFindSelectionCommand(GrepFinder):
    pattern = None

    def is_enabled(self):
        if self.view.element() is None:
            return self.get_selection() is not None
        return False

    def run(self, edit):
        if self.pattern is None:
            if self.get_selection() is None:
                return
        self.grep(self.pattern, self.selection.a)

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


class PatternInputHandler(sublime_plugin.TextInputHandler):
    def placeholder(self):
        return 'Pattern'

    def initial_text(self):
        return ''

    def validate(self, pattern):
        if pattern:
            return True
        return False


class GrepFindInputCommand(GrepFinder):
    def run(self, edit, pattern):
        self.grep(pattern)

    def input(self, args):
        return PatternInputHandler()


class GrepSummarizeSelectionsCommand(sublime_plugin.TextCommand):
    def is_enabled(self):
        return self.view.has_non_empty_selection_region()

    def run(self, edit):
        summarize_regions_with_context(
            self.view,
            self.view.sel(),
            )


class GrepGotoCommand(sublime_plugin.TextCommand):
    def run_(self, edit_token, args):
        fallback = False
        element = self.view.element()
        if element != 'output:output':
            fallback = True
        else:
            syntax = self.view.settings().get('syntax')
            if syntax != 'GrepStyleFind.sublime-syntax':
                fallback = True
        if fallback:
            fallback_command = args.get('command')
            if fallback_command:
                new_args = dict({'event': args['event']}.items())
                new_args.update(dict(args['args'].items()))
                self.view.run_command(fallback_command, new_args)
            return
        event = args['event']
        point = self.view.window_to_text((event['x'], event['y']))
        clicked_line_begin = self.view.line(point).begin()
        row, col = self.view.rowcol(clicked_line_begin)
        if row == 1:
            return
        main_view = sublime.View(self.view.settings().get('main_view.id'))
        if row > 1:
            coord_reg = self.view.find(r'\d+:\d+', clicked_line_begin)
            coord_txt = self.view.substr(coord_reg)
            row, col = map(int, coord_txt.split(':'))
            point = main_view.text_point(row - 1, col - 1)
        else:
            point = self.view.settings().get('main_view.header_jump_point')
            if point is None:
                return
        main_view.show_at_center(point)
        main_view.sel().clear()
        main_view.sel().add(point)
        self.view.window().focus_view(main_view)


class GrepSetFindOptionCommand(sublime_plugin.ApplicationCommand):
    def run(self, option):
        options = Settings.storage.get('find_options', {})
        options[option] = not options.get(option)
        Settings.storage.set('find_options', options)
        Settings.save()

    def is_checked(self, option):
        return Settings.storage.get('find_options', {}).get(option, False)


class Settings:
    FILE_NAME = 'GrepStyleFind.sublime-settings'

    @classmethod
    def load(cls):
        cls.color = cls.storage.get('color', 'region.purplish')
        cls.panel_settings = cls.storage.get('output_panel_settings', {})
        cls.auto_select = cls.storage.get('auto_select', True)
        cls.word_separators = cls.storage.get('word_separators', '')
        cls.max_line_length = cls.storage.get('max_line_length', 100)

    @classmethod
    def save(cls):
        sublime.save_settings(cls.FILE_NAME)

    @classmethod
    def reload(cls):
        cls.storage = sublime.load_settings(cls.FILE_NAME)
        cls.storage.add_on_change('__grep_style_find__', cls.load)
        cls.load()

    @classmethod
    def unload(cls):
        cls.storage.clear_on_change('__grep_style_find__')


def plugin_loaded():
    sublime.set_timeout_async(Settings.reload)


def plugin_unloaded():
    Settings.unload()
