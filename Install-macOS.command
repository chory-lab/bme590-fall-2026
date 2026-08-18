#!/bin/sh
# Double-click me on macOS. This is only a wrapper around install.sh in the
# same folder, so that Finder can launch it in Terminal.
#
# If macOS says the file "cannot be opened because it is from an unidentified
# developer", right-click it and choose Open -- or run the one-line command in
# the README instead, which is not subject to that check.
cd "$(dirname "$0")" || exit 1
sh ./install.sh "$@"
status=$?
echo
if [ "$status" -ne 0 ]; then echo "Installer exited with code $status."; fi
echo "You can close this window."
exit "$status"
