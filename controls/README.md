# Preorder Automation Controls

This directory contains configuration files that govern preorder tagging, overrides, automation toggles, and notifications.

## Files

- `pub_dates_overrides.csv` — Manual pub date corrections by ISBN
- `tag_rules.csv` — Rules for how tags are added or removed based on inventory and pub date
- `automation_flags.json` — Master switches to control automation features
- `release_email_template.md` — Markdown template for release notification emails

All files are loaded during GitHub workflows and used to inform reporting, tagging, and Shopify behavior.
