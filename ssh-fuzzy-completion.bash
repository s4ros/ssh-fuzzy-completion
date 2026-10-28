# Load bash-completion's lazy SSH completion, if available, before wrapping it.
if ! complete -p ssh >/dev/null 2>&1 && declare -F _completion_loader >/dev/null; then
  _completion_loader ssh >/dev/null 2>&1 || :
fi

_ssh_fuzzy_original_spec=$(complete -p ssh 2>/dev/null || :)
_ssh_fuzzy_install=1
_ssh_fuzzy_completion_options=(-o default)
if [[ $_ssh_fuzzy_original_spec == *'-o nospace'* ]]; then
  _ssh_fuzzy_completion_options+=(-o nospace)
fi
if [[ $_ssh_fuzzy_original_spec =~ -F[[:space:]]+([^[:space:]]+) ]]; then
  if [[ ${BASH_REMATCH[1]} == _ssh_fuzzy_complete ]]; then
    _ssh_fuzzy_install=0
  else
    _ssh_fuzzy_original_completion=${BASH_REMATCH[1]}
  fi
elif [[ -z $_ssh_fuzzy_original_spec ]]; then
  _ssh_fuzzy_no_completion() { COMPREPLY=(); }
  _ssh_fuzzy_original_completion=_ssh_fuzzy_no_completion
else
  # Do not replace a completion that cannot be delegated to a function.
  _ssh_fuzzy_original_completion=
fi

if (( _ssh_fuzzy_install )) && [[ -n $_ssh_fuzzy_original_completion ]]; then
  _ssh_fuzzy_complete() {
    local current=${COMP_WORDS[COMP_CWORD]} word flags flag selected user= query
    local i j expects_argument=0 end_options=0 split_user_index=-1

    # Bash may split user@host into three completion words. Readline keeps
    # the username but replaces @host.
    if (( COMP_CWORD >= 3 )) && [[ ${COMP_WORDS[COMP_CWORD-1]} == @ ]]; then
      split_user_index=$((COMP_CWORD - 2))
    fi

    # Delegate options, option arguments and remote commands.
    for ((i = 1; i < COMP_CWORD; i++)); do
      if (( i == split_user_index )); then
        ((i++))
        continue
      fi
      word=${COMP_WORDS[i]}
      if (( expects_argument )); then
        expects_argument=0
        continue
      fi
      if (( end_options )); then
        "$_ssh_fuzzy_original_completion" "$@"
        return
      fi
      if [[ $word == -- ]]; then
        end_options=1
      elif [[ $word == -* && $word != - ]]; then
        flags=${word:1}
        for ((j = 0; j < ${#flags}; j++)); do
          flag=${flags:j:1}
          # An alternate config changes the list of hosts.
          if [[ $flag == F ]]; then
            "$_ssh_fuzzy_original_completion" "$@"
            return
          fi
          if [[ $flag == [BbcDEeIiJLlmOoPpQRSWw] ]]; then
            (( j == ${#flags} - 1 )) && expects_argument=1
            break
          fi
        done
      else
        "$_ssh_fuzzy_original_completion" "$@"
        return
      fi
    done

    if (( expects_argument )) || [[ $current == -* && $end_options == 0 ]]; then
      "$_ssh_fuzzy_original_completion" "$@"
      return
    fi

    query=$current
    if (( split_user_index >= 0 )); then
      user=@
    fi
    if [[ $query == *@* ]]; then
      user=${query%%@*}@
      query=${query#*@}
    fi
    selected=$(python3 "$HOME/.config/ssh-fuzzy-hosts.py" |
      fzf --no-multi --height=40% --reverse --prompt='SSH host> ' --query="$query")
    if [[ -n $selected ]]; then
      COMPREPLY=("$user$selected")
      compopt +o nospace
    elif (( split_user_index >= 0 )); then
      compopt -o nospace
      COMPREPLY=("@$current")
    else
      compopt -o nospace
      COMPREPLY=("$current")
    fi
  }

  complete "${_ssh_fuzzy_completion_options[@]}" -F _ssh_fuzzy_complete ssh
fi
unset _ssh_fuzzy_original_spec _ssh_fuzzy_install _ssh_fuzzy_completion_options
