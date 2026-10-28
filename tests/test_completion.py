import fcntl
import os
import pty
import select
import shutil
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = ("ssh-fuzzy-completion.bash", "ssh-fuzzy-hosts.py")


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ssh-fuzzy-tests-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        (self.home / ".ssh" / "config.d").mkdir(parents=True)
        (self.home / ".config").mkdir()
        for name in FILES:
            shutil.copyfile(ROOT / name, self.home / ".config" / name)
        (self.home / ".ssh" / "config").write_text(
            "Host central-standby-01 alias-two *.example !excluded # comment\n"
            "HostName not-an-alias\nInclude config.d/*.conf\n"
        )
        (self.home / ".ssh" / "config.d" / "one.conf").write_text(
            'Host "included-server" alias-two\nInclude config.d/two.conf\n'
        )
        (self.home / ".ssh" / "config.d" / "two.conf").write_text(
            "HOST nested-server\nInclude config.d/one.conf\n"
        )
        self.env = dict(os.environ, HOME=str(self.home), TERM="xterm-256color")
        for key in ("FZF_DEFAULT_OPTS", "FZF_DEFAULT_OPTS_FILE", "FZF_DEFAULT_COMMAND"):
            self.env.pop(key, None)

    def test_host_aliases_and_nested_includes(self):
        result = subprocess.run(
            ["python3", str(ROOT / FILES[1])], env=self.env, text=True,
            capture_output=True, check=True,
        )
        self.assertEqual(result.stdout.splitlines(), [
            "central-standby-01", "alias-two", "included-server", "nested-server",
        ])

    def test_original_completion_and_repeated_sourcing(self):
        script = f'''
            original() {{ COMPREPLY=(); }}
            complete -F original ssh
            source "{ROOT / FILES[0]}"
            source "{ROOT / FILES[0]}"
            printf '%s\\n' "$_ssh_fuzzy_original_completion"
            complete -p ssh
        '''
        result = subprocess.run(["bash", "--noprofile", "--norc", "-c", script],
                                env=self.env, text=True, capture_output=True, check=True)
        self.assertIn("original\n", result.stdout)
        self.assertIn("-F _ssh_fuzzy_complete ssh", result.stdout)
        self.assertNotIn("-o nospace", result.stdout)

    @unittest.skipUnless(Path("/usr/share/bash-completion/bash_completion").exists(),
                         "system bash-completion is not installed")
    def test_lazy_bash_completion_is_loaded_before_wrapping(self):
        script = f'''
            source /usr/share/bash-completion/bash_completion
            source "{ROOT / FILES[0]}"
            printf '%s\\n' "$_ssh_fuzzy_original_completion"
            complete -p ssh
        '''
        result = subprocess.run(["bash", "--noprofile", "--norc", "-c", script],
                                env=self.env, text=True, capture_output=True, check=True)
        self.assertIn("_ssh\n", result.stdout)
        self.assertIn("-F _ssh_fuzzy_complete ssh", result.stdout)

    def test_no_previous_completion(self):
        script = f'source "{ROOT / FILES[0]}"; complete -p ssh'
        result = subprocess.run(["bash", "--noprofile", "--norc", "-c", script],
                                env=self.env, text=True, capture_output=True, check=True)
        self.assertIn("-F _ssh_fuzzy_complete ssh", result.stdout)

    def test_non_function_completion_is_preserved(self):
        script = f'complete -W "one two" ssh; source "{ROOT / FILES[0]}"; complete -p ssh'
        result = subprocess.run(["bash", "--noprofile", "--norc", "-c", script],
                                env=self.env, text=True, capture_output=True, check=True)
        self.assertIn("-W 'one two' ssh", result.stdout)

    @staticmethod
    def read_until(fd, target, seconds=8):
        output = b""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            ready, _, _ = select.select([fd], [], [], end - time.monotonic())
            if not ready:
                break
            chunk = os.read(fd, 65536)
            output += chunk
            # Answer fzf's terminal cursor-position requests in the test PTY.
            if b"\x1b[6n" in chunk:
                os.write(fd, b"\x1b[1;1R" * chunk.count(b"\x1b[6n"))
            if target in output:
                return output
        raise AssertionError(f"Expected {target!r}; got {output[-2000:]!r}")

    def run_terminal_case(self, text, expected, cancel=False, delegated=False):
        rc = self.home / "test.bashrc"
        rc.write_text(f'''\
PS1='READY> '
ssh() {{ printf 'SSH_ARGS'; printf ' <%s>' "$@"; printf '\\n'; }}
original() {{ COMPREPLY=("ORIGINAL_COMPLETION"); }}
complete -o default -o nospace -F original ssh
source "{ROOT / FILES[0]}"
''')
        pid, fd = pty.fork()
        if pid == 0:
            os.execvpe("bash", ["bash", "--noprofile", "--rcfile", str(rc), "-i"], self.env)
        try:
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
            self.read_until(fd, b"READY> ")
            os.write(fd, text.encode() + b"\t")
            if delegated:
                self.read_until(fd, b"ORIGINAL_COMPLETION")
            else:
                self.read_until(fd, b"central-")
                os.write(fd, b"\x1b" if cancel else b"\r")
                # Let fzf finish processing the selection before pressing Enter.
                time.sleep(0.3)
            os.write(fd, b"\r")
            output = self.read_until(fd, b"READY> ")
            self.assertIn(expected, output)
        finally:
            os.close(fd)
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)

    @unittest.skipUnless(shutil.which("fzf"), "fzf is required for terminal tests")
    def test_interactive_completion(self):
        cases = [
            ("ssh standby", b"SSH_ARGS <central-standby-01>", False, False),
            ("ssh -p 2222 user@standby", b"SSH_ARGS <-p> <2222> <user@central-standby-01>", False, False),
            ("ssh user@standby", b"SSH_ARGS <user@standby>", True, False),
            ("ssh -i key", b"SSH_ARGS <-i> <ORIGINAL_COMPLETION>", False, True),
            ("ssh some-host command", b"SSH_ARGS <some-host> <ORIGINAL_COMPLETION>", False, True),
            ("ssh -F other.conf standby", b"SSH_ARGS <-F> <other.conf> <ORIGINAL_COMPLETION>", False, True),
        ]
        for text, expected, cancel, delegated in cases:
            with self.subTest(text=text, cancel=cancel):
                self.run_terminal_case(text, expected, cancel, delegated)


@unittest.skipUnless(shutil.which("fzf"), "fzf is required by the installer")
class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="ssh-fuzzy-installer-")
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.env = dict(os.environ, HOME=str(self.home))

    def install(self, *args):
        return subprocess.run(["bash", str(ROOT / "install.sh"), *args],
                              env=self.env, text=True, capture_output=True)

    def test_install_is_idempotent_and_switchable(self):
        for _ in range(2):
            result = self.install()
            self.assertEqual(result.returncode, 0, result.stderr)
        rc = (self.home / ".bashrc").read_text()
        self.assertEqual(rc.count("# >>> ssh-fuzzy-completion >>>"), 1)
        for name in FILES:
            self.assertEqual((self.home / ".config" / name).read_bytes(), (ROOT / name).read_bytes())
        for value in ("1", "0"):
            test_rc = self.home / f"test-{value}.bashrc"
            test_rc.write_text(rc.replace("SSH_FUZZY_COMPLETION=1", f"SSH_FUZZY_COMPLETION={value}"))
            script = f'original() {{ :; }}; complete -F original ssh; source "{test_rc}"; complete -p ssh'
            result = subprocess.run(["bash", "--noprofile", "--norc", "-c", script],
                                    env=self.env, text=True, capture_output=True, check=True)
            expected = "_ssh_fuzzy_complete" if value == "1" else "original"
            self.assertIn(f"-F {expected} ssh", result.stdout)

    def test_conflict_does_not_overwrite_and_force_is_explicit(self):
        config = self.home / ".config"
        config.mkdir()
        existing = config / FILES[0]
        existing.write_text("custom content\n")
        result = self.install()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(existing.read_text(), "custom content\n")
        self.assertFalse((config / FILES[1]).exists())
        self.assertFalse((self.home / ".bashrc").exists())
        result = self.install("--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(existing.read_bytes(), (ROOT / FILES[0]).read_bytes())

    def test_symlink_is_never_replaced(self):
        config = self.home / ".config"
        config.mkdir()
        target = self.home / "important"
        target.write_text("keep\n")
        (config / FILES[0]).symlink_to(target)
        result = self.install("--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "keep\n")

    def test_existing_source_block_is_not_duplicated(self):
        original = 'SSH_FUZZY_COMPLETION=0\nsource "$HOME/.config/ssh-fuzzy-completion.bash"\n'
        (self.home / ".bashrc").write_text(original)
        result = self.install()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / ".bashrc").read_text(), original)

    def test_piped_installer_downloads_both_files(self):
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        curl = bin_dir / "curl"
        curl.write_text('#!/usr/bin/env bash\ncp -- "$TEST_REPO/${2##*/}" "$4"\n')
        curl.chmod(0o755)
        env = dict(self.env, PATH=f"{bin_dir}:{self.env['PATH']}", TEST_REPO=str(ROOT))
        result = subprocess.run(["bash", "-s"], input=(ROOT / "install.sh").read_text(),
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in FILES:
            self.assertEqual((self.home / ".config" / name).read_bytes(), (ROOT / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
