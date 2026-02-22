#!/usr/bin/env python
# License: GPLv3 Copyright: 2024, Kovid Goyal <kovid at kovidgoyal.net>

from . import BaseTest


def sample_data(extra_modes=None, mouse=None):
    modes = {
        '': {
            'Copy/paste': [
                {'key': 'ctrl+shift+c', 'action': 'copy_to_clipboard'},
                {'key': 'ctrl+shift+v', 'action': 'paste_from_clipboard'},
                {'key': 'ctrl+shift+s', 'action': 'paste_from_selection'},
            ],
            'Scrolling': [
                {'key': 'ctrl+shift+up', 'action': 'scroll_line_up'},
                {'key': 'ctrl+shift+down', 'action': 'scroll_line_down'},
            ],
            'Window management': [
                {'key': 'ctrl+shift+enter', 'action': 'new_window'},
            ],
        }
    }
    if extra_modes:
        modes.update(extra_modes)
    return {'modes': modes, 'mouse': mouse or []}


def strip_all_ansi(handler, lines):
    return '\n'.join(handler._strip_ansi(x) for x in lines)


class TestShowKeys(BaseTest):

    def test_collect_keys_data(self):
        from kittens.show_keys.main import collect_keys_data
        from kitty.actions import groups
        opts = self.set_options()
        data = collect_keys_data(opts)
        self.assertIn('modes', data)
        self.assertIn('mouse', data)
        self.assertIn('', data['modes'], 'Default keyboard mode should be present')
        default_mode = data['modes']['']
        # Should have at least some categories
        self.assertTrue(len(default_mode) > 0, 'Should have at least one category')
        # All category names should be from the known groups
        known_titles = set(groups.values())
        for cat_name in default_mode:
            self.assertIn(cat_name, known_titles, f'Unknown category: {cat_name}')
        # Each category should have bindings with key and action
        for cat_name, bindings in default_mode.items():
            self.assertIsInstance(bindings, list)
            for b in bindings:
                self.assertIn('key', b)
                self.assertIn('action', b)
                self.assertIsInstance(b['key'], str)
                self.assertIsInstance(b['action'], str)
                self.assertTrue(len(b['key']) > 0)
                self.assertTrue(len(b['action']) > 0)
        # Mouse mappings
        self.assertIsInstance(data['mouse'], list)
        for b in data['mouse']:
            self.assertIn('key', b)
            self.assertIn('action', b)

    def test_collect_keys_categories_ordered(self):
        from kittens.show_keys.main import collect_keys_data
        from kitty.actions import groups
        opts = self.set_options()
        data = collect_keys_data(opts)
        default_mode = data['modes']['']
        cat_names = list(default_mode.keys())
        group_titles = list(groups.values())
        # Categories should appear in the same order as defined in groups
        indices = []
        for cat in cat_names:
            if cat in group_titles:
                indices.append(group_titles.index(cat))
        self.ae(indices, sorted(indices), 'Categories should be ordered according to groups dict')

    def test_collect_keys_bindings_sorted(self):
        from kittens.show_keys.main import collect_keys_data
        opts = self.set_options()
        data = collect_keys_data(opts)
        for cat_name, bindings in data['modes'][''].items():
            keys = [b['key'] for b in bindings]
            self.ae(keys, sorted(keys), f'Bindings in {cat_name} should be sorted by key')

    def test_handler_build_display_lines(self):
        from kittens.show_keys.main import ShowKeys
        data = sample_data()
        handler = ShowKeys(data)
        handler._build_display_lines()
        lines = handler.display_lines
        self.assertTrue(len(lines) > 0)
        # Should contain the title
        raw = strip_all_ansi(handler, lines)
        self.assertIn('Kitty Keyboard Shortcuts', raw)
        # Should contain category headers
        self.assertIn('Copy/paste', raw)
        self.assertIn('Scrolling', raw)
        self.assertIn('Window management', raw)
        # Should contain actual bindings
        self.assertIn('ctrl+shift+c', raw)
        self.assertIn('copy_to_clipboard', raw)
        self.assertIn('scroll_line_up', raw)

    def test_handler_build_display_lines_with_mouse(self):
        from kittens.show_keys.main import ShowKeys
        mouse = [
            {'key': 'left press ungrabbed', 'action': 'mouse_selection normal'},
            {'key': 'ctrl+left press ungrabbed', 'action': 'mouse_selection rectangle'},
        ]
        data = sample_data(mouse=mouse)
        handler = ShowKeys(data)
        handler._build_display_lines()
        raw = strip_all_ansi(handler, handler.display_lines)
        self.assertIn('Mouse actions', raw)
        self.assertIn('mouse_selection normal', raw)

    def test_handler_build_display_lines_with_extra_mode(self):
        from kittens.show_keys.main import ShowKeys
        extra = {
            'vim': {
                'Miscellaneous': [
                    {'key': 'h', 'action': 'move_left'},
                    {'key': 'j', 'action': 'move_down'},
                ],
            }
        }
        data = sample_data(extra_modes=extra)
        handler = ShowKeys(data)
        handler._build_display_lines()
        raw = strip_all_ansi(handler, handler.display_lines)
        self.assertIn('vim', raw)
        self.assertIn('move_left', raw)

    def test_handler_filter(self):
        from kittens.show_keys.main import ShowKeys
        data = sample_data()
        handler = ShowKeys(data)
        handler._build_display_lines()
        total = len(handler.display_lines)

        # Filter for 'clipboard' should reduce lines
        handler.search_text = 'clipboard'
        handler._apply_filter()
        self.assertTrue(len(handler.filtered_lines) < total)
        # Filtered lines should contain matching bindings
        raw = strip_all_ansi(handler, handler.filtered_lines)
        self.assertIn('clipboard', raw.lower())

        # Filter for nonsense should show only structural lines
        handler.search_text = 'zzzznonexistent'
        handler._apply_filter()
        for line in handler.filtered_lines:
            stripped = handler._strip_ansi(line).strip()
            if stripped:
                # Should only be header/separator lines
                self.assertTrue(
                    '\u2500' in line or 'Kitty Keyboard Shortcuts' in handler._strip_ansi(line),
                    f'Unexpected non-matching line: {stripped}'
                )

        # Clear filter restores all lines
        handler.search_text = ''
        handler._apply_filter()
        self.ae(len(handler.filtered_lines), total)

    def test_strip_ansi(self):
        from kittens.show_keys.main import ShowKeys
        self.ae(ShowKeys._strip_ansi('\033[32mhello\033[39m'), 'hello')
        self.ae(ShowKeys._strip_ansi('no escapes'), 'no escapes')
        self.ae(ShowKeys._strip_ansi('\033[1;32mBold green\033[0m'), 'Bold green')
        self.ae(ShowKeys._strip_ansi(''), '')
