#!/usr/bin/env bash
set -euo pipefail

force=0
case "${1:-}" in
  '') ;;
  --force) force=1 ;;
  *) printf 'Usage: bash install.sh [--force]\n' >&2; exit 2 ;;
esac
if (( $# > 1 )); then
  printf 'Usage: bash install.sh [--force]\n' >&2
  exit 2
fi

for dependency in python3 fzf; do
  if ! command -v "$dependency" >/dev/null 2>&1; then
    printf 'Missing dependency: %s. Install it and try again.\n' "$dependency" >&2
    exit 1
  fi
done

tmpdir=$(mktemp -d "${TMPDIR:-/tmp}/ssh-fuzzy-completion.XXXXXXXX")
cleanup() {
  rm -f -- "$tmpdir/ssh-fuzzy-completion.bash" "$tmpdir/ssh-fuzzy-hosts.py"
  rmdir -- "$tmpdir"
}
trap cleanup EXIT

source_dir=
if [[ -n ${BASH_SOURCE[0]:-} && -f ${BASH_SOURCE[0]} ]]; then
  source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
fi
files=(ssh-fuzzy-completion.bash ssh-fuzzy-hosts.py)
if [[ -n $source_dir && -f $source_dir/${files[0]} && -f $source_dir/${files[1]} ]]; then
  for file in "${files[@]}"; do
    cp -- "$source_dir/$file" "$tmpdir/$file"
  done
else
  if ! command -v curl >/dev/null 2>&1; then
    printf 'Missing dependency: curl. Install it and try again.\n' >&2
    exit 1
  fi
  base_url=https://raw.githubusercontent.com/s4ros/ssh-fuzzy-completion/main
  for file in "${files[@]}"; do
    curl -fsSL "$base_url/$file" -o "$tmpdir/$file"
  done
fi

# Check every destination before changing any of them.
for file in "${files[@]}"; do
  destination=$HOME/.config/$file
  if [[ -L $destination || ( -e $destination && ! -f $destination ) ]]; then
    printf 'Refusing to overwrite a symlink or non-file: %s\n' "$destination" >&2
    exit 1
  fi
  if [[ -f $destination ]] && ! cmp -s -- "$tmpdir/$file" "$destination" && (( ! force )); then
    printf 'Existing file differs: %s\nReview it and rerun with --force to replace it.\n' "$destination" >&2
    exit 1
  fi
done

mkdir -p -- "$HOME/.config"
for file in "${files[@]}"; do
  destination=$HOME/.config/$file
  if [[ ! -f $destination ]] || ! cmp -s -- "$tmpdir/$file" "$destination"; then
    cp -- "$tmpdir/$file" "$destination"
  fi
done

bashrc=$HOME/.bashrc
if [[ -f $bashrc ]] && grep -Eq '^[[:space:]]*(source|\.)[[:space:]]+.*ssh-fuzzy-completion\.bash' "$bashrc"; then
  printf 'Existing SSH fuzzy completion configuration found in %s; leaving it unchanged.\n' "$bashrc"
else
  cat >> "$bashrc" <<'EOF'

# >>> ssh-fuzzy-completion >>>
# Set to 0 and start a new shell to disable.
SSH_FUZZY_COMPLETION=1
if [[ $SSH_FUZZY_COMPLETION == 1 ]] && command -v fzf >/dev/null && command -v python3 >/dev/null; then
  source "$HOME/.config/ssh-fuzzy-completion.bash"
fi
# <<< ssh-fuzzy-completion <<<
EOF
fi

printf 'Installed. Start a new Bash shell, then try: ssh standby<Tab>\n'
