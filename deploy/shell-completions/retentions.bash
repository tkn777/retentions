# bash completion for retentions
# install to: /usr/share/bash-completion/completions/retentions

_retentions() {
    local cur prev
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    local opts="
        --regex-mode
        --age-type
        --protect
        --hours
        --days
        --weeks
        --months
        --quarters
        --week13
        --years
        --last
        --max-size
        --max-files
        --max-age
        --list-only
        --verbose
        --dry-run
        --no-lock-file
        --fail-on-delete-error
        --delete-companions
        --version
        --help
    "

    case "$prev" in
        --regex-mode)
            COMPREPLY=( $(compgen -W "casesensitive ignorecase" -- "$cur") )
            return
            ;;
        --age-type)
            COMPREPLY=( $(compgen -W "ctime mtime atime" -- "$cur") )
            return
            ;;
        --verbose)
            COMPREPLY=( $(compgen -W "ERROR WARN INFO DEBUG 0 1 2 3" -- "$cur") )
            return
            ;;
    esac

    # option completion
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$opts" -- "$cur") )
        return
    fi

    # positional arguments
    # 1st: path
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -d -- "$cur") )
        return
    fi

    # 2nd: file_pattern -> intentionally no completion
    if [[ $COMP_CWORD -eq 2 ]]; then
        COMPREPLY=()
        return
    fi
}

complete -o filenames -F _retentions retentions
