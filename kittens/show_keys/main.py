#!/usr/bin/env python
# License: GPLv3 Copyright: 2024, Kovid Goyal <kovid at kovidgoyal.net>


import json
import sys
from typing import Any

from kitty.key_encoding import EventType
from kitty.typing_compat import KeyEventType, ScreenSize

from ..tui.handler import Handler
from ..tui.line_edit import LineEdit
from ..tui.loop import Loop
from ..tui.operations import styled


class ShowKeys(Handler):

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.scroll_offset = 0
        self.search_mode = False
        self.search_text = ''
        self.line_edit = LineEdit()
        self.display_lines: list[str] = []
        self.filtered_lines: list[str] = []

    def initialize(self) -> None:
        self.cmd.set_cursor_visible(False)
        self.cmd.set_line_wrapping(False)
        self._build_display_lines()
        self.draw_screen()

    def _build_display_lines(self) -> None:
        lines: list[str] = []
        lines.append('')
        lines.append(styled('Kitty Keyboard Shortcuts', bold=True, fg='gray', fg_intense=True))
        lines.append('')

        modes = self.data.get('modes', {})
        for mode_name, categories in modes.items():
            if mode_name:
                lines.append('')
                lines.append(styled(f'  Keyboard Mode: {mode_name}', bold=True, fg='magenta'))
                lines.append('')

            for category, bindings in categories.items():
                if not bindings:
                    continue
                lines.append('')
                sep = '\u2500' * 40
                lines.append(styled(f'  \u2500\u2500 {category} {sep}', fg='blue', fg_intense=True))
                lines.append('')
                for b in bindings:
                    key = b['key']
                    action = b['action']
                    key_styled = styled(f'    {key:30s}', fg='green')
                    lines.append(f'{key_styled}{action}')

        mouse = self.data.get('mouse', [])
        if mouse:
            lines.append('')
            sep = '\u2500' * 40
            lines.append(styled(f'  \u2500\u2500 Mouse actions {sep}', fg='blue', fg_intense=True))
            lines.append('')
            for b in mouse:
                key = b['key']
                action = b['action']
                key_styled = styled(f'    {key:30s}', fg='green')
                lines.append(f'{key_styled}{action}')

        lines.append('')
        self.display_lines = lines
        self.filtered_lines = lines

    def _apply_filter(self) -> None:
        if not self.search_text:
            self.filtered_lines = self.display_lines
            return
        query = self.search_text.lower()
        filtered: list[str] = []
        for line in self.display_lines:
            # Always include blank/header/separator lines, or lines matching query
            stripped = self._strip_ansi(line).lower()
            if not stripped.strip() or '\u2500' in line or query in stripped:
                filtered.append(line)
        self.filtered_lines = filtered

    @staticmethod
    def _strip_ansi(text: str) -> str:
        import re
        return re.sub(r'\033\[[^m]*m', '', text)

    @property
    def max_scroll(self) -> int:
        available = self.screen_size.rows - 2  # header + footer
        return max(0, len(self.filtered_lines) - available)

    def draw_screen(self) -> None:
        self.cmd.clear_screen()
        rows = self.screen_size.rows
        cols = self.screen_size.cols
        available = rows - 1  # leave 1 line for footer

        start = self.scroll_offset
        end = start + available
        visible = self.filtered_lines[start:end]

        for line in visible:
            self.print(line)

        # Move to last row for footer
        self.print()
        if self.search_mode:
            footer = f'  /{self.line_edit.current_input}█'
        else:
            search_info = f'  Filter: {self.search_text}  ' if self.search_text else ''
            pos = f'{self.scroll_offset + 1}/{max(1, len(self.filtered_lines))}'
            footer_parts = [
                styled('[/]', fg='yellow') + ' Search  ',
                styled('[q]', fg='yellow') + ' Quit  ',
                styled('[j/k]', fg='yellow') + ' Scroll  ',
                styled('[Esc]', fg='yellow') + ' Clear',
            ]
            footer = '  '.join(footer_parts) + f'  {search_info}' + styled(pos, dim=True)
        self.cmd.set_cursor_position(rows, 0)
        self.write(f'\r{footer[:cols]}')

    def on_key_event(self, key_event: KeyEventType, in_bracketed_paste: bool = False) -> None:
        if key_event.type is EventType.RELEASE:
            return
        if not self.search_mode and key_event.matches('shift+space'):
            self._scroll(-(self.screen_size.rows - 2))
            return
        if key_event.text:
            self.on_text(key_event.text, in_bracketed_paste)
        else:
            self.on_key(key_event)

    def on_text(self, text: str, in_bracketed_paste: bool = False) -> None:
        if self.search_mode:
            self.line_edit.on_text(text, in_bracketed_paste)
            self.search_text = self.line_edit.current_input
            self._apply_filter()
            self.scroll_offset = 0
            self.draw_screen()
            return
        text = text.lower()
        if text == 'q':
            self.quit_loop(0)
        elif text == 'j':
            self._scroll(1)
        elif text == 'k':
            self._scroll(-1)
        elif text == ' ':
            self._scroll(self.screen_size.rows - 2)
        elif text == 'g':
            self.scroll_offset = 0
            self.draw_screen()
        elif text == '/':
            self.search_mode = True
            self.line_edit.clear()
            self.cmd.set_cursor_visible(True)
            self.draw_screen()

    def on_key(self, key_event: KeyEventType) -> None:
        if key_event.type is EventType.RELEASE:
            return
        if self.search_mode:
            if key_event.matches('escape'):
                self.search_mode = False
                self.cmd.set_cursor_visible(False)
                self.draw_screen()
                return
            if key_event.matches('enter'):
                self.search_mode = False
                self.cmd.set_cursor_visible(False)
                self.draw_screen()
                return
            if key_event.matches('backspace'):
                self.line_edit.backspace()
                self.search_text = self.line_edit.current_input
                self._apply_filter()
                self.scroll_offset = 0
                self.draw_screen()
                return
            return
        if key_event.matches('escape'):
            if self.search_text:
                self.search_text = ''
                self.line_edit.clear()
                self._apply_filter()
                self.scroll_offset = 0
                self.draw_screen()
            else:
                self.quit_loop(0)
            return
        if key_event.matches('down') or key_event.matches('j'):
            self._scroll(1)
        elif key_event.matches('up') or key_event.matches('k'):
            self._scroll(-1)
        elif key_event.matches('page_down'):
            self._scroll(self.screen_size.rows - 2)
        elif key_event.matches('page_up'):
            self._scroll(-(self.screen_size.rows - 2))
        elif key_event.matches('home'):
            self.scroll_offset = 0
            self.draw_screen()
        elif key_event.matches('end'):
            self.scroll_offset = self.max_scroll
            self.draw_screen()

    def _scroll(self, delta: int) -> None:
        new = max(0, min(self.scroll_offset + delta, self.max_scroll))
        if new != self.scroll_offset:
            self.scroll_offset = new
            self.draw_screen()

    def on_resize(self, screen_size: ScreenSize) -> None:
        super().on_resize(screen_size)
        self.scroll_offset = min(self.scroll_offset, self.max_scroll)
        self.draw_screen()

    def on_interrupt(self) -> None:
        self.quit_loop(0)

    def on_eot(self) -> None:
        self.quit_loop(0)


help_text = 'Display all current keybindings'
usage = ''


def main(args: list[str]) -> None:
    if sys.stdin.isatty():
        data = _collect_keys_data()
    else:
        raw = sys.stdin.read()
        data = json.loads(raw)

    loop = Loop()
    handler = ShowKeys(data)
    loop.loop(handler)
    raise SystemExit(loop.return_code)


def _collect_keys_data() -> dict[str, Any]:
    """Collect keybinding data when run standalone (not via boss action)."""
    from kitty.config import load_config
    opts = load_config()
    return collect_keys_data(opts)


def collect_keys_data(opts: Any) -> dict[str, Any]:
    """Collect all keybinding data from options into a JSON-serializable dict."""
    from kitty.actions import get_all_actions, groups
    from kitty.options.utils import KeyDefinition, KeyboardMode
    from kitty.types import Shortcut

    # Build action->group lookup
    action_to_group: dict[str, str] = {}
    for group_key, actions in get_all_actions().items():
        for action in actions:
            action_to_group[action.name] = groups[group_key]

    modes: dict[str, dict[str, list[dict[str, str]]]] = {}

    def as_sc(k: 'Any', v: KeyDefinition) -> Shortcut:
        if v.is_sequence:
            return Shortcut((v.trigger,) + v.rest)
        return Shortcut((k,))

    for mode_name, mode in opts.keyboard_modes.items():
        categories: dict[str, list[dict[str, str]]] = {}
        for key, defns in mode.keymap.items():
            # Use last non-duplicate definition
            seen: set[tuple[Any, ...]] = set()
            uniq: list[KeyDefinition] = []
            for d in reversed(defns):
                uid = d.unique_identity_within_keymap
                if uid not in seen:
                    seen.add(uid)
                    uniq.append(d)
            for d in uniq:
                sc = as_sc(key, d)
                key_repr = sc.human_repr(opts.kitty_mod)
                action_repr = d.human_repr()
                # Determine category from first word of action definition
                action_name = d.definition.split()[0] if d.definition else 'no_op'
                category = action_to_group.get(action_name, 'Miscellaneous')
                categories.setdefault(category, []).append({
                    'key': key_repr,
                    'action': action_repr,
                })
        # Sort within categories
        for cat in categories:
            categories[cat].sort(key=lambda b: b['key'])
        # Order categories by the groups order
        ordered: dict[str, list[dict[str, str]]] = {}
        for group_title in groups.values():
            if group_title in categories:
                ordered[group_title] = categories.pop(group_title)
        # Add any remaining
        for cat_name, binds in sorted(categories.items()):
            ordered[cat_name] = binds
        modes[mode_name] = ordered

    # Mouse mappings
    mouse: list[dict[str, str]] = []
    for event, action in opts.mousemap.items():
        key_repr = event.human_repr(opts.kitty_mod)
        mouse.append({'key': key_repr, 'action': action})
    mouse.sort(key=lambda b: b['key'])

    return {'modes': modes, 'mouse': mouse}


if __name__ == '__main__':
    main(sys.argv)
elif __name__ == '__doc__':
    cd = sys.cli_docs  # type: ignore
    cd['usage'] = usage
    cd['options'] = ''.format
    cd['help_text'] = help_text
    cd['short_desc'] = help_text
