#!/usr/bin/env bash
# Reproduce a reviewed app branch, tag or full commit in a fresh image directory.
set -euo pipefail
destination="${1:?destination required}"
repository="${2:?repository required}"
revision="${3:?branch, tag or full commit required}"
git check-ref-format --allow-onelevel "$revision"
test ! -e "$destination"
git init -q "$destination"
git -C "$destination" remote add origin "$repository"
git -C "$destination" fetch --depth 1 origin "$revision"
git -C "$destination" checkout -q --detach FETCH_HEAD
