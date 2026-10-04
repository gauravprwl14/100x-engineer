# Login spec

Sessions must be revocable immediately on logout.
Uses redis as the session_store.

## Acceptance criteria

AC-1: After logout, a request carrying the ended session gets 401 on its next call. (R2)
AC-2: After a password change or an admin ban, the user's existing sessions get 401 on their next request. (R3)
