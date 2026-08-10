# Lessons

- When a subscription setting is saved asynchronously, prevent dependent queue actions until the save response is committed and reflected in the local cache.
- For verified fixes in this repository, integrate directly to `origin/main` without waiting for a separate merge/push instruction.
- Trace every job-creation endpoint independently; re-summarize can bypass subscription queue logic and must preserve the prompt context explicitly.
