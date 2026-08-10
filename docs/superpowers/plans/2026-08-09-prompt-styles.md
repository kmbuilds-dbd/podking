# Prompt Styles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add private, labeled analysis prompt styles, assign them to subscriptions, and snapshot the selected prompt onto queued jobs.

**Architecture:** Add a user-owned `PromptStyle` model with a protected `general` row. Subscriptions reference a style; jobs copy the style's prompt text at enqueue time into `analysis_prompt`, and the worker uses that snapshot. Keep `UserSettings.system_prompt` as a compatibility mirror while new prompt-style APIs become canonical.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, Alembic/PostgreSQL, Pydantic, React/TypeScript, TanStack Query, pytest/pytest-asyncio, Vite.

## Global Constraints

- Prompt styles must be private to the owning user.
- `general` must exist for every user, remain editable, and never be deletable.
- Deleting a custom style must reassign its subscriptions to `general` atomically.
- Manual URL and resummarize jobs use `general`; subscription jobs use the subscription's selected style.
- The prompt text must be snapshotted when a job is queued.
- Existing summaries must retain `Summary.system_prompt` behavior.
- Preserve the unrelated untracked `AGENTS.md` file.

---

### Task 1: Add the prompt-style data model and migration

**Files:**
- Modify: `backend/podking/models.py`
- Modify: `backend/podking/schemas.py`
- Create: `backend/podking/prompt_styles.py`
- Create: `backend/alembic/versions/0009_prompt_styles.py`
- Test: `tests/test_prompt_styles.py`

**Interfaces:**
- `PromptStyle(user_id, label, prompt_text)` owns a user's labeled prompt.
- `Subscription.prompt_style_id` references `PromptStyle.id`.
- `Job.analysis_prompt` stores the queue-time text snapshot and is nullable only for legacy rows.
- `ensure_general_prompt_style(db, user)` creates or returns the user's `general` style and synchronizes the compatibility `UserSettings.system_prompt` when the general style is edited.

- [ ] **Step 1: Write failing migration/model tests**

Add tests that run against migrated PostgreSQL and assert:

```python
async def test_migration_backfills_general_and_subscription_assignment(migrated_engine):
    async with get_sessionmaker()() as db:
        user = (await db.execute(select(User))).scalar_one()
        style = (await db.execute(select(PromptStyle).where(
            PromptStyle.user_id == user.id,
            PromptStyle.label == "general",
        ))).scalar_one()
        sub = (await db.execute(select(Subscription).where(
            Subscription.user_id == user.id,
        ))).scalar_one_or_none()
        assert style.prompt_text == user.settings.system_prompt
        assert sub is None or sub.prompt_style_id == style.id
```

Also assert the ORM columns exist and custom labels are unique per user.

- [ ] **Step 2: Run the focused tests and verify they fail for the missing model/schema**

Run: `uv run pytest tests/test_prompt_styles.py -q`

Expected: FAIL because `PromptStyle` and the migration-backed columns do not exist.

- [ ] **Step 3: Implement the model and migration**

Add `PromptStyle` and user/subscription relationships. Add `prompt_style_id` and `analysis_prompt` to the ORM models. In migration `0009`:

1. Create `prompt_styles` with UUID primary key, user foreign key, label, prompt text, timestamps, and a `(user_id, label)` unique constraint.
2. Insert one `general` row for every existing user using `user_settings.system_prompt`.
3. Add nullable `subscriptions.prompt_style_id`, backfill it by joining each subscription's user to that user's `general` row, then make it non-null and add the foreign key.
4. Add nullable `jobs.analysis_prompt` for legacy compatibility.

Implement `ensure_general_prompt_style` so test fixtures and newly-created users receive a general row even if they predate the helper.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `uv run pytest tests/test_prompt_styles.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the data model**

```bash
git add backend/podking/models.py backend/podking/schemas.py backend/alembic/versions/0009_prompt_styles.py tests/test_prompt_styles.py
git commit -m "feat: add per-user prompt styles"
```

### Task 2: Add prompt-style and subscription assignment APIs

**Files:**
- Create: `backend/podking/api/prompt_styles.py`
- Modify: `backend/podking/main.py`
- Modify: `backend/podking/api/settings.py`
- Modify: `backend/podking/api/subscriptions.py`
- Modify: `backend/podking/schemas.py`
- Test: `tests/test_prompt_styles.py`
- Test: `tests/test_subscriptions.py`

**Interfaces:**
- `GET /api/prompt-styles` returns only the current user's styles ordered with `general` first.
- `POST /api/prompt-styles` accepts `{label, prompt_text}` and returns the created style.
- `PATCH /api/prompt-styles/{style_id}` accepts optional `{label, prompt_text}`.
- `DELETE /api/prompt-styles/{style_id}` reassigns subscriptions to general and returns `204`; deleting general returns `409`.
- `PATCH /api/subscriptions/{sub_id}` accepts `{prompt_style_id}` and returns the updated subscription.

- [ ] **Step 1: Write failing API tests**

Cover creating/listing/editing/deleting styles, duplicate labels, cross-user access, general deletion rejection, subscription fallback after deletion, and cross-user subscription-style assignment rejection. Update subscription response assertions to include the selected style.

- [ ] **Step 2: Run focused API tests and verify expected failures**

Run: `uv run pytest tests/test_prompt_styles.py tests/test_subscriptions.py -q`

Expected: FAIL on missing routes and response fields.

- [ ] **Step 3: Implement the endpoints**

Use the authenticated user in every query. Keep `/api/settings`'s existing `system_prompt` field mapped to the general style for compatibility, add `prompt_styles` to its response, and make `PATCH /api/settings` update the general style when `system_prompt` is supplied. Validate labels and prompt text before writing. Make custom-style deletion update all owned subscriptions to general before deleting the style in one transaction.

- [ ] **Step 4: Run focused API tests and verify they pass**

Run: `uv run pytest tests/test_prompt_styles.py tests/test_subscriptions.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the APIs**

```bash
git add backend/podking/api backend/podking/main.py backend/podking/schemas.py tests/test_prompt_styles.py tests/test_subscriptions.py
git commit -m "feat: manage and assign prompt styles"
```

### Task 3: Snapshot prompts when jobs are queued and consume them in the worker

**Files:**
- Modify: `backend/podking/api/jobs.py`
- Modify: `backend/podking/api/subscriptions.py`
- Modify: `backend/podking/worker/runner.py`
- Modify: `tests/test_jobs.py`
- Modify: `tests/test_subscriptions.py`
- Create: `tests/test_worker.py`

**Interfaces:**
- Every newly-created summarization `Job` has `analysis_prompt` set before commit.
- `_summarize_and_embed(job_id, user_id, episode_id, transcript_text, analysis_prompt)` passes the supplied snapshot to Claude and persists it on `Summary.system_prompt`.
- Legacy jobs with null `analysis_prompt` fall back to the user's general prompt.

- [ ] **Step 1: Write failing queue and worker tests**

Add tests that:

```python
async def test_subscription_job_snapshots_selected_prompt(...):
    # assign a custom style to a subscription, queue its episode,
    # edit the style, then assert the job retains the original text
    assert job.analysis_prompt == "original custom guidance"
```

Also assert manual and resummarize jobs snapshot general, and worker tests capture the prompt passed to `claude_client.summarize` and the prompt persisted on the summary.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `uv run pytest tests/test_jobs.py tests/test_subscriptions.py tests/test_worker.py -q`

Expected: FAIL because jobs do not store or consume `analysis_prompt`.

- [ ] **Step 3: Implement queue-time selection and worker consumption**

Add a small queue helper that resolves a subscription style or general style for the current user and returns the prompt text. Set `analysis_prompt` in manual, resummarize, and subscription job constructors. Change the worker's summarization step to accept the snapshot and use the general-style fallback only for legacy null values. Do not alter TTS jobs.

- [ ] **Step 4: Run focused tests and verify they pass**

Run: `uv run pytest tests/test_jobs.py tests/test_subscriptions.py tests/test_worker.py -q`

Expected: PASS.

- [ ] **Step 5: Commit the queue/worker behavior**

```bash
git add backend/podking/api/jobs.py backend/podking/api/subscriptions.py backend/podking/worker/runner.py tests/test_jobs.py tests/test_subscriptions.py tests/test_worker.py
git commit -m "feat: snapshot prompt styles on jobs"
```

### Task 4: Update Settings and subscription detail UI

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/pages/SubscriptionDetail.tsx`

**Interfaces:**
- Settings can list, create, edit, and delete prompt styles.
- Subscription detail can select and save one of the user's prompt styles.

- [ ] **Step 1: Update typed API functions and frontend tests/checks**

Add TypeScript types and request helpers for prompt styles and subscription assignment. Keep the existing settings save behavior working for general, API keys, and TTS voice IDs.

- [ ] **Step 2: Implement the Settings UI**

Render general as the existing Analysis style guidance editor. Add a compact custom-style editor with label, textarea, Save, Add style, and Delete actions. Invalidate settings/style queries after mutations and display API errors inline.

- [ ] **Step 3: Implement the subscription detail selector**

Load prompt styles, render a selector near the subscription heading, default to the response's current style, and save changes via `PATCH /api/subscriptions/{id}`. Invalidate the subscription detail/list queries after success.

- [ ] **Step 4: Verify the frontend**

Run: `npm run build`

Expected: PASS with no TypeScript errors.

Run: `npm run lint`

Expected: only the three pre-existing lint errors remain; do not expand scope to fix them.

- [ ] **Step 5: Commit the UI**

```bash
git add frontend/src/api.ts frontend/src/pages/Settings.tsx frontend/src/pages/SubscriptionDetail.tsx
git commit -m "feat: add prompt style controls"
```

### Task 5: Full verification and handoff

**Files:**
- Modify: `tasks/todo.md`

- [ ] **Step 1: Run the full backend suite**

Run: `uv run pytest -q`

Expected: all tests pass.

- [ ] **Step 2: Run backend lint/type checks**

Run: `uv run ruff check backend tests`

Expected: no new violations.

- [ ] **Step 3: Run the frontend build and lint**

Run: `cd frontend && npm run build && npm run lint`

Expected: build passes; lint reports only the documented pre-existing errors.

- [ ] **Step 4: Inspect the final diff and repository state**

Run: `git diff main...HEAD --stat && git status --short --branch`

Confirm only feature files, design/plan docs, and `tasks/todo.md` changed; `AGENTS.md` remains untracked and untouched.

- [ ] **Step 5: Update the checklist and commit verification notes**

Record test results and any known lint baseline in `tasks/todo.md`, then commit the final documentation update.
