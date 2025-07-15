#!/bin/bash

echo "🔄 Syncing with Codex's latest branch..."

# Step 1: Make sure you're on your working branch
git checkout codex-sync-work || exit 1

# Step 2: Fetch all remote branches
git fetch origin

# Step 3: Rebase Codex's latest into your local work
echo "Rebasing origin/codex/kickoff-refactor-project-and-scaffold-sync_preorders.py into codex-sync-work..."
git rebase origin/codex/kickoff-refactor-project-and-scaffold-sync_preorders.py

# Step 4: Push updated codex-sync-work to remote if rebase succeeded
if [ $? -eq 0 ]; then
  echo "✅ Rebase successful. Pushing to origin..."
  git push origin codex-sync-work --force-with-lease
  echo "🚀 Deployed codex-sync-work is now up to date!"
else
  echo "⚠️ Rbease failed. Please resolve conflicts manually."
fi
