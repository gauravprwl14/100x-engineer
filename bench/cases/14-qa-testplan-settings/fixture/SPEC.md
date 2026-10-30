# Workspace settings

Each workspace has a settings page at `/workspaces/<id>/settings`.

## Acceptance criteria

- AC-1: Admins and members of a workspace can open its settings page and see the workspace name and default timezone.
- AC-2: Admins can rename the workspace. The name is required and at most 60 characters.
- AC-3: Admins can change the default timezone to any IANA timezone (for example `Europe/Berlin`).
- AC-4: Admins can delete the workspace.
- AC-5: Members cannot change the settings.
- AC-6: People outside the workspace cannot see its settings page.
