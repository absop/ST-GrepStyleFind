import sublime
import sublime_plugin


class GrepPanelGotoCommand(sublime_plugin.TextCommand):
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
            fallback_command = args["command"] if "command" in args else None
            if fallback_command:
                new_args = dict({"event": args["event"]}.items())
                new_args.update(dict(args["args"].items()))
                self.view.run_command(fallback_command, new_args)
            return
        event = args["event"]
        point = self.view.window_to_text((event["x"], event["y"]))
        coord_reg = self.view.find(r'\d+:\d+', self.view.line(point).begin())
        coord_txt = self.view.substr(coord_reg)
        row, col = map(int, coord_txt.split(':'))
        view_id = self.view.settings().get('associated_view_id')
        view = sublime.View(view_id)
        point = view.text_point(row - 1, col - 1)
        view.show_at_center(point)
        view.sel().clear()
        view.sel().add(point)
        self.view.window().focus_view(view)


class GrepStyleFindCommand(sublime_plugin.TextCommand):
    pattern = None

    def is_visible(self):
        return self.get_selection() is not None

    def run(self, edit, literal=True, ignorecase=True):
        if self.pattern is None:
            if self.get_selection() is None:
                return
        self.grep(literal, ignorecase)

    def get_selection(self):
        view = self.view
        selections = view.sel()
        self.pattern = None
        if selections:
            region = selections[0]
            if not region.empty():
                content = view.substr(region)
                if content.strip() and '\n' not in content:
                    self.pattern = content
            if self.pattern is None and self.auto_select:
                region = view.word(region)
                word = view.substr(region).strip(self.word_separators)
                if len(word) > 0:
                    self.pattern = word
        return self.pattern

    def grep(self, literal, ignorecase):
        flags = 0
        if literal:
            flags |= sublime.FindFlags.LITERAL
        if ignorecase:
            flags |= sublime.FindFlags.IGNORECASE
        view = self.view
        results = []
        max_row = 0
        max_col = 0
        for region in view.find_all(self.pattern, flags):
            row, col = view.rowcol(region.a)
            row += 1
            col += 1
            line = view.line(region)
            results.append((row, col, region, line))
            if row > max_row:
                max_row = row
            if col > max_col:
                max_col = col
        Region = sublime.Region
        wr = len(str(max_row))
        wc = len(str(max_col))
        col_offset = wr + 1 + wc + 2
        stat = f"{len(results)} occurrences of '"
        begin = len(stat)
        stat += self.pattern
        end = len(stat)
        stat += "'\n"
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
        panel = window.create_output_panel('GrepStyleFind')
        panel.assign_syntax('GrepStyleFind.sublime-syntax')
        panel.settings().set('associated_view_id', view.id())
        panel.set_read_only(False)
        panel.run_command('append', {'characters': result_text})
        panel.set_read_only(True)
        panel.add_regions('*grep*', highlight_regions,
            scope=self.color,
            flags=sublime.DRAW_OUTLINED
            )
        window.run_command('show_panel', {'panel': 'output.GrepStyleFind'})

    @classmethod
    def init(cls):
        cls.color = settings.get('color', 'region.purplish')
        cls.auto_select = settings.get('auto_select', True)
        cls.word_separators = settings.get('word_separators', '')


def reload_settings():
    global settings
    settings = sublime.load_settings('GrepStyleFind.sublime-settings')
    settings.add_on_change('__grep_panel__', GrepStyleFindCommand.init)
    GrepStyleFindCommand.init()


def plugin_loaded():
    sublime.set_timeout_async(reload_settings)


def plugin_unloaded():
    settings.clear_on_change('__grep_panel__')
