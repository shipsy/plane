# Ticket Master — Consolidated API Contract

## Background

Today, creating a "Ticket Master" in Plane from the n8n flow requires three sequential API calls:

1. `POST /api/v1/workspaces/{slug}/issue-type/` — create the issue type.
2. `POST /api/v1/workspaces/{slug}/issue-type/{issue_type_id}/custom-properties/` — called once per custom property (N requests).
3. `GET` + `POST /api/v1/workspaces/{slug}/projects/DEFAULT/members/` — list project members, then one POST per missing assignee.

Because these are three independent HTTP calls, there is no shared transaction. If call 1 succeeds and call 2 or 3 fails, the issue type row is already committed. The n8n flow has no way to undo it, the user retries with the same name, and they hit `409 Issue Type with same name already exists` — stuck.

This proposal consolidates the three flows into a single project-level endpoint that:

- accepts one request body containing the issue type, all custom properties, and all assignees,
- performs all three operations inside one `transaction.atomic()` block on the server,
- rolls everything back if any step fails, leaving the DB in its pre-request state.

The endpoint is scoped to the project (not the workspace) because assignee creation requires `project_id` for project-member assignment. Issue type and custom properties remain workspace-scoped under the hood; only the URL is project-rooted.

---

## Endpoint

```
POST /api/v1/workspaces/{slug}/projects/{project_id}/ticket-master/
```

Headers:

| Header | Value |
|---|---|
| `x-api-key` | Plane API key |
| `Content-Type` | `application/json` |

`project_id` accepts both a real project uuid and the literal string `DEFAULT`. `BaseAPIView.check_kwargs` in `apiserver/plane/api/views/base.py` already intercepts `"DEFAULT"` for any view that subclasses `BaseAPIView` and rewrites it to the `TICKET` project's uuid for the workspace — no extra code in the new view.

---

## Request body

```json
{
  "issue_type": {
    "name": "string (required)",
    "description": "string (optional)"
  },
  "custom_properties": [
    {
      "name": "string (required)",
      "value": "string (optional — defaults to name)",
      "is_required": false,
      "data_type": "string | number | dropdown | ..."
    }
  ],
  "assignees": [
    {
      "first_name": "string",
      "last_name": "string",
      "email": "string (required)",
      "display_name": "string"
    }
  ]
}
```

### Field semantics

| Field | Required | Notes |
|---|---|---|
| `issue_type.name` | Yes | Unique per workspace. |
| `issue_type.description` | No | Free text. |
| `custom_properties` | No | May be empty / omitted. Created in one transaction. |
| `custom_properties[].name` | Yes | Unique per issue type. |
| `custom_properties[].data_type` | Yes | Same values accepted by the existing endpoint. |
| `assignees` | No | May be empty / omitted. |
| `assignees[].first_name` | No | Used only when the user has to be created. |
| `assignees[].last_name` | No | Used only when the user has to be created. |
| `assignees[].email` | Yes | Lower-cased server-side. Used as the primary key for lookup. |
| `assignees[].display_name` | No | Used only when the user has to be created. |

Field order in the `assignees` payload mirrors the existing n8n call (`first_name`, `last_name`, `email`, `display_name`) so the caller-side shape doesn't change. `role`, `hub_codes`, and `username` are **not** part of the contract — they fall through to the existing server-side defaults (`role = 15`, `hub_codes = []`, `username = uuid`), same as today.

---

## Success response — `201 Created`

```json
{
  "issue_type": {
    "id": "uuid",
    "name": "...",
    "description": "...",
    "...": "full IssueTypeSerializer payload"
  },
  "custom_properties": [
    {
      "id": "uuid",
      "name": "...",
      "data_type": "...",
      "is_required": false,
      "...": "full IssueTypeCustomPropertySerializer payload"
    }
  ],
  "assignees": [
    {
      "id": "uuid",
      "email": "...",
      "first_name": "...",
      "...": "full UserLiteSerializer payload"
    }
  ]
}
```

### Behavior per section

**`issue_type`** — required. Same name-uniqueness rule as the current standalone endpoint (one name per workspace). If the name is already taken, the endpoint short-circuits with `409` before opening the transaction — `custom_properties` and `assignees` are **not** processed in that case.

**`custom_properties`** — bulk-created against the newly created issue type. The view loops the existing `IssueTypeCustomPropertySerializer` once per element (the same serializer the standalone endpoint uses). All-or-nothing inside the single transaction.

**`assignees`** — for each entry, the server runs the same logic as today's `ProjectMemberAPIEndpoint.post`, with one mandatory behavior change:

1. `email` must be present → otherwise the whole request errors out with `400 "Invalid assignees"` and the offending index.
2. `validate_email(email)` → invalid email errors the request out the same way.
3. Workspace + project are resolved once for the whole request (not per-assignee).
4. Lookup the user by `email.lower()`.
5. **If the user exists and is already a project member → no-op, just include them in the response.** The standalone endpoint returns `400 "User is already part of the workspace and project"` here; the consolidated endpoint must NOT, because this is the normal case for most assignees in the n8n flow.
6. If the user doesn't exist → `create_user(...)` plus a `Profile` (`last_workspace_id`, `onboarding_step.profile_complete = True`, `onboarding_step.workspace_join = True`, `is_tour_completed = True`, `is_onboarded = True`, `company_name = workspace.name`). Identical to the existing `post`.
7. If `hub_codes` was sent for an existing user → update `user.hub_codes`. (Not in the n8n payload today, so this branch is dormant but preserved.)
8. If no workspace membership exists → `create_workspace_member(workspace.id, user, role)`.
9. If no project membership exists → `create_project_member(project.id, user, role)`.

The response returns the resolved list (existing + newly created users) for the emails in the request — matching the n8n script's final filter, which is now done server-side.

---

## Error responses

Designed so the n8n caller can map cleanly to today's `PlaneError` flow.

| Case | Status | Body |
|---|---|---|
| Workspace or project missing | `400` | `{"error": "Provided workspace or project does not exist"}` |
| Issue type name already exists | `409` | `{"error": "Issue Type with same name already exists", "id": "<existing uuid>"}` |
| Issue type payload invalid | `400` | `{"error": "Invalid issue_type", "details": {…serializer errors}}` |
| One or more custom properties invalid | `400` | `{"error": "Invalid custom_properties", "details": [{"index": 0, "errors": {…}}, …]}` |
| Custom property name duplicate (DB level) | `410` | `{"error": "Invalid custom_properties", "details": [{"index": 1, "name": "The Property Name is already taken"}]}` |
| Assignee email missing or invalid | `400` | `{"error": "Invalid assignees", "details": [{"index": 0, "email": "Invalid email provided"}]}` |

Every error case above (except the `400` for missing workspace/project and the `409` for duplicate issue-type name, which short-circuit before the transaction opens) triggers a full rollback. Nothing is committed.

---

## Transactionality (hard requirement)

All three write steps — issue type, custom properties, assignees — run inside **one single `transaction.atomic()` block**. Not three nested blocks, not three sequential blocks. **One.** All three succeed together, or nothing is persisted.

### Why one block (not three)

If each step had its own `atomic()` that committed independently, a failure in step 2 would leave step 1 already on disk — bringing back the orphan-issue-type bug this whole consolidation is designed to fix.

With a single outer `atomic()` wrapping all three writes, any exception anywhere in the chain triggers one Postgres `ROLLBACK`. The DB returns to its pre-request state and the caller can retry the same payload.

### View structure

```python
def post(self, request, slug, project_id):
    # ---- pre-flight validation (OUTSIDE the transaction) ----
    # read-only checks — nothing to roll back, so no reason to open a tx for them
    workspace = Workspace.objects.filter(slug=slug).first()
    project   = Project.objects.filter(pk=project_id).first()
    if not workspace or not project:
        return Response({"error": "..."}, status=400)

    # short-circuit on duplicate issue-type name BEFORE opening the tx
    existing = IssueType.objects.filter(
        name=request.data["issue_type"]["name"], workspace=workspace
    ).first()
    if existing:
        return Response(
            {"error": "Issue Type with same name already exists", "id": str(existing.id)},
            status=409,
        )

    # ---- ONE atomic block wrapping all three writes ----
    try:
        with transaction.atomic():
            # 1. issue type
            issue_type = self._create_issue_type(workspace, ...)

            # 2. all custom properties (loop, same serializer as standalone endpoint)
            created_properties = self._create_custom_properties(issue_type, ...)

            # 3. all assignees (loop, reuses ProjectMemberAPIEndpoint helpers)
            resolved_assignees = self._resolve_assignees(workspace, project, ...)

    except ValidationError as e:
        # any failure inside the block -> whole tx rolled back, nothing committed
        return Response({"error": "...", "details": e.detail}, status=400)
    except IntegrityError as e:
        return Response({"error": "...", "details": str(e)}, status=400)

    # ---- only reached after the whole block committed ----
    return Response({
        "issue_type":        IssueTypeSerializer(issue_type).data,
        "custom_properties": created_properties,
        "assignees":         resolved_assignees,
    }, status=201)
```

### Atomicity guarantees

- Issue type insert is rolled back if any custom property or assignee step fails.
- All custom properties are committed together or not at all — partial inserts are rolled back if any single property is invalid.
- User / workspace-member / project-member rows created during assignee handling are rolled back too.
- Existing users that were only *looked up* (not created) are never touched.
- The response body is constructed and returned only after the transaction commits.

### What lives inside vs outside the block

| Step | Inside `atomic()`? | Reason |
|---|---|---|
| Workspace + project lookup | No | Read-only, nothing to roll back |
| Duplicate-name `409` short-circuit | No | Read-only; lets us skip opening a tx for the common conflict case |
| Issue type insert | Yes | Write |
| Custom property loop | Yes | Writes |
| Assignee loop (user / workspace member / project member inserts) | Yes | Writes |
| Response serialization | No | Pure in-memory work after commit |

### Side effects beyond the DB

Any non-DB side effect (Celery tasks like `issue_activity.delay(...)`, webhooks, emails) must be scheduled via `transaction.on_commit(lambda: ...)` so they only fire if the transaction actually commits. The existing `IssueTypeAPIEndpoint.post` has those `.delay` calls commented out today, so this is not a current concern — flagging it in case they get re-enabled later.

---

## Server-side reuse

Nothing new is invented for the underlying operations — the new view orchestrates existing building blocks:

| Operation | Reused component |
|---|---|
| Base view + `DEFAULT` resolution | `BaseAPIView` (provides `check_kwargs` rewrite of `project_id == "DEFAULT"`) |
| Issue type creation | `IssueTypeSerializer` (with workspace-id context, same as `IssueTypeAPIEndpoint.post`) |
| Custom property creation | `IssueTypeCustomPropertySerializer` (with issue-type-id context, same as `IssueTypeCustomPropertyAPIEndpoint.post`) |
| User creation | `ProjectMemberAPIEndpoint.create_user` |
| Profile setup for new users | Same fields written as `ProjectMemberAPIEndpoint.post` (`last_workspace_id`, `onboarding_step`, `is_tour_completed`, `is_onboarded`, `company_name`) |
| Workspace membership | `ProjectMemberAPIEndpoint.create_workspace_member` |
| Project membership | `ProjectMemberAPIEndpoint.create_project_member` |
| Response shape | `UserLiteSerializer` for assignees, existing serializers' `.data` for the rest |

The standalone endpoints (`/issue-type/...`, `/projects/<id>/members/...`) remain in place for PATCH / DELETE / GET and other callers — only the create-flow is consolidated.

---

## Caller migration (n8n flow)

### Before

```js
const issue_type_id = await create_issue_type(...)
await Promise.all(
  custom_properties.map(cp => createCustomProperty(issue_type_id, cp))
)
const existing = await getProjectMembers()
await Promise.all(missing.map(createAssignee))
```

Three round-trips, plus N per custom property, plus 1 + M for assignees. No rollback on partial failure.

### After

```js
const res = await axios.post(
  `${PLANE_URL}/api/v1/workspaces/${org_id}/projects/DEFAULT/ticket-master/`,
  {
    issue_type:        { name, description },
    custom_properties: [ ... ],
    assignees:         [ ... ],
  },
  { headers }
)

ticket_master.ticket_type_id        = res.data.issue_type.id
ticket_master.feilds_to_be_captured = res.data.custom_properties  // re-attach dropdownSourceField client-side
ticket_master.assignees             = res.data.assignees
```

One round-trip. Atomic on failure. The caller no longer maintains its own loops or its own "missing users" diff against the existing project members.

The `dropdownSourceField` / `dropdownFieldSourceType` re-attachment (currently done client-side after custom-property creation) stays client-side — it's not part of Plane's model.

---

## Resolved decisions

- **Issue-type name conflict** — if the issue type name already exists, return `409` with the existing id (matches the standalone endpoint's behavior). `custom_properties` and `assignees` are **not** processed in that case. Since orphan issue types can no longer happen (atomic transaction), a `409` here always indicates a real duplicate.
- **`DEFAULT` in the URL** — works out of the box because `BaseAPIView.check_kwargs` rewrites `project_id == "DEFAULT"` to the `TICKET` project's uuid before any view handler runs. The n8n caller's existing URL shape (`…/projects/DEFAULT/...`) keeps working without change.
- **Assignee payload shape** — `first_name`, `last_name`, `email`, `display_name` in that order, matching the existing n8n call. `role` is not part of the contract; the server applies its existing default (`15`).
- **Already-a-project-member assignees** — silent no-op in the consolidated endpoint (not a `400`), because for the n8n flow this is the normal case, not a client mistake.
