#!/usr/bin/env bash
set -euo pipefail

export FIREBASE_CLI_HOME="/tmp/piyasalens-firebase"
firebase deploy --project piyasalens --only functions
