# SSH fuzzy completion for Bash

Find SSH aliases from your SSH configuration with `fzf`, directly from the Bash command line:

```text
ssh standby<Tab>
```

Select a host with the arrow keys and press Enter to insert it. Press Enter again to run SSH, or Esc to cancel. Matching is fuzzy, so the query can occur anywhere in the alias. `user@standby` also works.

## Requirements

- Bash 4.3 or later, OpenSSH, Python 3, and [fzf](https://github.com/junegunn/fzf)
- curl for the remote installer

## Install

Review the installer first if you prefer:

```bash
curl -fsSL https://raw.githubusercontent.com/s4ros/ssh-fuzzy-completion/main/install.sh
```

Then install:

```bash
curl -fsSL https://raw.githubusercontent.com/s4ros/ssh-fuzzy-completion/main/install.sh | bash
```

Start a new Bash shell, or run `exec bash` in the current one. Installation copies two files into `~/.config/` and adds a switch to `~/.bashrc`. It does not modify your SSH configuration or connect to any host.

Alternatively, run `bash install.sh` from a clone. Reinstalling the same version is safe. If a destination file differs, the installer stops without replacing it; after reviewing your changes, use `bash install.sh --force` from the clone, or:

```bash
curl -fsSL https://raw.githubusercontent.com/s4ros/ssh-fuzzy-completion/main/install.sh | bash -s -- --force
```

`--force` replaces differing installed files. Symlinks and non-files at those paths are never replaced.

## Enable or disable

Change the switch in `~/.bashrc`:

```bash
SSH_FUZZY_COMPLETION=1  # 1: enabled, 0: disabled
```

Start a new Bash shell after changing it. To uninstall, remove the `ssh-fuzzy-completion` block from `~/.bashrc`, then remove `~/.config/ssh-fuzzy-completion.bash` and `~/.config/ssh-fuzzy-hosts.py`. If an existing setup was detected during installation, remove that setup's own source block instead.

## How it works

The host list is read on each completion from explicit `Host` aliases in `~/.ssh/config`, including files referenced by `Include` (relative paths are resolved under `~/.ssh`; globs, `~`, nested includes and cycles are handled). Wildcard and negated `Host` patterns are excluded because they are not concrete names. This is a lightweight configuration reader, not a full OpenSSH evaluator: it does not expand environment variables or SSH tokens in `Include`, and it does not evaluate conditional `Match` blocks.

Existing function-based SSH completion is preserved for options, option arguments, remote commands and `ssh -F`; `scp` is unchanged. If bash-completion uses lazy loading, its SSH completion is loaded before wrapping. With no existing SSH completion, host selection still works and other arguments fall back to Bash's default completion. An existing non-function SSH completion is left untouched.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
