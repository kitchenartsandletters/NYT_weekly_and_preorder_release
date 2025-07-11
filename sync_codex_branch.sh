#!/bin/bash

# Auto-sync codex-sync-work branch with remote

echo "Fetching latest changes from origin..."
git fetch origin

echo "Rebasing local codex-sync-work onto origin/codex-sync-work..."
git rebase origin/codex-sync-work

if [ $? -eq 0 ]; then
  echo "Rebase successful. Pushing to origin..."
  git push origin codex-sync-work
  echo "✅ Sync complete!"
else
  echo "⚠️ Rebase failed. Please resolve conflicts manually."
fi
