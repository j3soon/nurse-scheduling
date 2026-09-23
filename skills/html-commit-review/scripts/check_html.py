#!/usr/bin/env python3
"""Check tag balance in one HTML file. Exits 1 on unclosed or mismatched tags."""

import sys
from html.parser import HTMLParser

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}


class Checker(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.errors = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f"stray </{tag}> at {self.getpos()}")
            return
        open_tag, pos = self.stack.pop()
        if open_tag != tag:
            self.errors.append(
                f"<{open_tag}> opened at {pos} closed by </{tag}> at {self.getpos()}"
            )


def main():
    if len(sys.argv) != 2:
        print("usage: check_html.py FILE.html", file=sys.stderr)
        return 2
    checker = Checker()
    with open(sys.argv[1], encoding="utf-8") as handle:
        checker.feed(handle.read())
    for tag, pos in checker.stack:
        print(f"unclosed <{tag}> opened at {pos}")
    for error in checker.errors:
        print(error)
    if checker.stack or checker.errors:
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
