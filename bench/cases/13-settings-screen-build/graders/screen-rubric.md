---
type: llm
focus: files
---
Hidden ground truth: a workspace settings screen with admins and members is expected to have these screen behaviours, whether or not the ticket names them:
A. Deleting the workspace asks for confirmation first. The confirmation names the workspace ("Acme Design") and says the deletion is permanent, its button repeats the verb ("Delete workspace", not "OK"), and Cancel leaves the workspace intact. For a deletion this large, typing the workspace name to enable the button is the strong form.
B. Members see the settings read-only: rename, timezone and delete controls are absent for them, or disabled with a reason ("Only admins can change settings").
C. Every changing handler (rename, timezone, delete) checks on the server that the caller is an admin of THIS workspace; hiding a button is not enough.
D. Leaving the page with unsaved edits warns the user (a beforeunload handler or an equivalent guard).
E. Save is disabled, or does nothing, until a field differs from the stored value.
F. An invalid timezone or empty name is refused with a message naming the field, and the other edits stay on screen.
G. The timezone change says before saving that it affects every member of the workspace.
H. Two admins saving at once are told about the conflict (a version or updated-at check) rather than one silently overwriting the other.
I. Changes are recorded with who made them and when (a settings history or audit entry).

Pass only if A holds AND at least two of E, F, G, H, I hold in the code. B, C and D are checked elsewhere and must not decide this grade. Fail if deletion runs on a single click, or its confirmation does not name the workspace.
