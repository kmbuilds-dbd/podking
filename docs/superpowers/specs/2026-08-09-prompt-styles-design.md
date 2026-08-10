# Per-user Analysis Prompt Styles

## Goal

Allow each user to create labeled analysis prompt styles, assign a style to each subscription, and guarantee that queued jobs use the prompt assigned at queue time.

## Approved behavior

- Prompt styles are private to one user and are never shared.
- Every user has an editable `general` style. It is created from the existing `user_settings.system_prompt` value.
- Custom style labels are unique per user and both labels and prompt text are editable.
- The `general` style cannot be deleted.
- Deleting a custom style reassigns every subscription using it to `general` in the same transaction.
- Existing subscriptions are assigned to `general` during migration.
- The subscription detail page owns prompt-style assignment.
- Subscription-created summary jobs use the subscription's selected style.
- Manual URL jobs and resummarization jobs use `general`.
- Each summary job snapshots the selected prompt text when it is queued. Worker execution never re-resolves a mutable style for that job.
- Existing summaries continue to store the exact prompt used in `summaries.system_prompt`.

## Data model

Add `prompt_styles` with user ownership, a label, prompt text, and timestamps. Enforce `(user_id, label)` uniqueness and a per-user `general` row through application-level creation and migration data backfill.

Add `subscriptions.prompt_style_id` as a non-null foreign key to `prompt_styles`. Add `jobs.analysis_prompt` as a non-null-at-runtime text snapshot, nullable in the database only for backward compatibility with jobs created before this migration. Keep `user_settings.system_prompt` as a compatibility mirror for existing callers and fixtures; the general prompt style is the canonical value for new APIs and job queueing.

## API and UI

- Extend Settings responses with the user's prompt-style collection while retaining `system_prompt` as the general-style compatibility field.
- Add authenticated prompt-style create, update, and delete operations with user ownership checks.
- Extend subscription responses with the selected style and add an authenticated subscription prompt-style update operation.
- Add a Settings editor for the general style and custom styles.
- Add a prompt-style selector to the subscription detail page.

## Queue and worker flow

Centralize prompt selection at enqueue time:

1. Ensure the user's general style exists.
2. Select the subscription style for subscription jobs, or general for manual/resummarize jobs.
3. Copy the selected prompt text into `Job.analysis_prompt`.
4. Pass the job snapshot through the summarization pipeline and save that same text on the resulting summary.

For legacy jobs whose snapshot is null, the worker falls back to the user's general style (and then the compatibility settings value) so deployment does not strand queued work.

## Verification

Backend tests cover migration backfill, prompt-style CRUD and ownership, delete fallback, subscription assignment, queue-time snapshots, and worker prompt usage. Frontend verification includes TypeScript compilation and production build; existing unrelated lint failures are reported separately.
