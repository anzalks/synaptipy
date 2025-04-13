#!/bin/bash

# Check if 'tree' command is available
if command -v tree &>/dev/null; then
    exec tree "$@"
else
    # Custom tree implementation
    print_tree() {
        local dir="$1"
        local indent="${2-}"
        local name
        local count
        local i

        # List all items in the directory
        local items=( "$dir"/* )
        # Check if the directory is empty
        if [ ! -e "${items[0]}" ]; then
            return
        fi

        count=${#items[@]}
        i=0

        for item in "${items[@]}"; do
            i=$((i+1))
            name=$(basename "$item")
            if [ $i -eq $count ]; then
                echo "${indent}└── $name"
                if [ -d "$item" ]; then
                    print_tree "$item" "${indent}    "
                fi
            else
                echo "${indent}├── $name"
                if [ -d "$item" ]; then
                    print_tree "$item" "${indent}│   "
                fi
            fi
        done
    }

    # Determine the starting directory (default: current directory)
    start_dir="${1:-.}"
    # Check if the path is a file
    if [ ! -d "$start_dir" ]; then
        echo "$start_dir"
        exit 0
    fi
    # Print the root directory and generate the tree
    echo "$start_dir"
    print_tree "$start_dir" ""
fi
