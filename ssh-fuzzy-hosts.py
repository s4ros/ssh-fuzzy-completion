#!/usr/bin/env python3
"""List explicit Host aliases from the user's SSH configuration."""

import glob
import os
import re
import shlex


def hosts(config_path):
    ssh_dir = os.path.expanduser("~/.ssh")
    seen_files = set()
    seen_hosts = set()

    def read_config(path):
        path = os.path.realpath(path)
        if path in seen_files:
            return
        seen_files.add(path)
        try:
            with open(path, encoding="utf-8") as config:
                lines = list(config)
        except (OSError, UnicodeError):
            return

        for line in lines:
            match = re.match(r"^\s*(Host|Include)(?:\s*=\s*|\s+)(.*)$", line, re.I)
            if not match:
                continue
            try:
                values = shlex.split(match.group(2), comments=True)
            except ValueError:
                continue
            if match.group(1).lower() == "host":
                for value in values:
                    if not any(char in value for char in "*?!") and value not in seen_hosts:
                        seen_hosts.add(value)
                        yield value
            else:
                for value in values:
                    pattern = os.path.expanduser(value)
                    if not os.path.isabs(pattern):
                        pattern = os.path.join(ssh_dir, pattern)
                    for included in sorted(glob.glob(pattern)):
                        yield from read_config(included)

    yield from read_config(config_path)


if __name__ == "__main__":
    for host in hosts(os.path.expanduser("~/.ssh/config")):
        print(host)
