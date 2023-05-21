import re

import sublime
import sublime_plugin


class GrepFindSelectionCommand(sublime_plugin.TextCommand):
    pattern = None
    max_line_width = 100

    def is_enabled(self):
        if self.view.element() is None:
            return self.get_selection() is not None
        return False

    def run(self, edit):
        if self.pattern is None:
            if self.get_selection() is None:
                return
        self.grep()

    def get_selection(self):
        view = self.view
        selections = view.sel()
        self.pattern = None
        self.selection = None
        if selections:
            region = selections[0]
            if not region.empty():
                if region.size() < self.max_line_width:
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
                if 0 < region.size() < self.max_line_width:
                    word = view.substr(region).strip(Settings.word_separators)
                    if len(word) > 0:
                        self.selection = view.find(word, region.begin(),
                            flags=sublime.FindFlags.LITERAL
                            )
                        self.pattern = word
        return self.pattern

    def grep(self):
        find_options = Settings.storage.get('find_options', {})
        case_sensitive = find_options.get('case_sensitive', False)
        regexp = find_options.get('regexp', False)
        whole_word = find_options.get('whole_word', False)

        flags = 0
        options = []
        pattern = self.pattern
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

        view = self.view
        results = []
        max_row = 0
        max_col = 0
        max_line_width = self.max_line_width
        for region in view.find_all(pattern, flags):
            row, col = view.rowcol(region.a)
            row += 1
            col += 1
            line = view.line(region)
            if line.size() > max_line_width:
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
        count = len(results)
        plurar = 'es' if count > 1 else ''
        stat = f"{count} match{plurar} of '"
        begin = len(stat)
        stat += self.pattern
        end = len(stat)
        if options:
            stat += f"' ({', '.join(options)})\n"
        else:
            stat += f"'\n"
        offset = len(stat)
        result_lines = [stat]
        highlight_regions = [Region(begin, end)]
        for row, col, region, line in results:
            linetext = view.substr(line)
            stripped = linetext.lstrip()
            indenter = len(linetext) - len(stripped)
            stripped = stripped.rstrip()
            # TODO: stripped should contain the matched word
            if len(stripped) > 100:
                stripped = stripped[:97] + '...'
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

        window = view.window()
        settings = Settings.panel_settings.copy()
        settings['main_view.id'] = view.id()
        settings['main_view.backpoint'] = self.selection.a
        panel = window.create_output_panel('GrepStyleFind')
        panel.assign_syntax('GrepStyleFind.sublime-syntax')
        panel.settings().update(settings)
        panel.set_read_only(False)
        panel.run_command('append', {'characters': result_text})
        panel.set_read_only(True)
        panel.add_regions('*grep*', highlight_regions,
            scope=Settings.color,
            flags=sublime.DRAW_OUTLINED
            )
        window.run_command('show_panel', {'panel': 'output.GrepStyleFind'})


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
            point = self.view.settings().get('main_view.backpoint')
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
