#!/bin/bash

# Auto-syncs the local codex-sync-work branch with Codex updates
# Usage: ./refactor/utils/sync_codex_branch.sh

set -e

echo "🔄 Fetching latest changes from origin..."
git fetch origin

echo "📋 Rebasing local codex-sync-work onto origin/codex-sync-work..."
git rebase origin/codex-sync-work

echo "🚀 Pushing rebased branch to origin..."
git push origin codex-sync-work

echo "✅ Sync complete!"
