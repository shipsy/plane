# Plane Permissions Reference

This document describes every permission role and access-control mechanism defined in the Plane codebase.

---

## 1. Role Hierarchy

Plane uses a **numeric role system** where higher values grant more authority. The same numeric values are used across workspace, project, and instance scopes.

| Role | Numeric Value | Summary |
|--------|---------------|--------------------------------------------------|
| **Admin** | 20 | Full administrative control |
| **Member** | 15 | Standard contributor access |
| **Guest** | 5 | Limited, read-mostly access |

These values are defined in:

- **Backend enum** — `apiserver/plane/app/permissions/base.py` (`ROLE` enum)
- **Backend constants** — `apiserver/plane/app/permissions/workspace.py` and `project.py`
- **Frontend enum** — `web/ce/constants/user-permissions/index.ts` (`EUserPermissions`)
- **TypeScript types** — `packages/types/src/enums.ts`

---

## 2. Permission Scopes

Plane enforces permissions at three distinct levels:

### 2.1 Instance Level

The topmost scope. Controls who can administer the self-hosted Plane instance.

| Role | Authority |
|------|-----------|
| **Instance Admin** (role ≥ 15) | Can configure the instance, manage settings, and perform global operations. Checked via `InstanceAdminPermission` (`apiserver/plane/license/api/permissions/instance.py`). |

### 2.2 Workspace Level

A workspace is the top-level organizational unit for teams.

| Role | Authority |
|------|-----------|
| **Admin** (20) | Full control: create, read, update, and **delete** the workspace and all its entities. Can manage members, billing, and settings. |
| **Member** (15) | Can create and update workspace entities. Can read all workspace data. **Cannot** delete the workspace itself. |
| **Guest** (5) | Read-only access to workspace data (e.g., dashboards). Cannot create, update, or delete workspace-level entities. |

### 2.3 Project Level

Projects live inside a workspace. Each user can have a different role per project.

| Role | Authority |
|------|-----------|
| **Admin** (20) | Full project control: update project settings, manage members, and perform all CRUD operations on project entities (issues, cycles, modules, pages, views, etc.). |
| **Member** (15) | Can create, read, and update project entities. Cannot modify project-level settings (name, description, etc.). |
| **Guest** (5) | Read access to project entities. Can create and update entities **only when explicitly allowed** by the permission class in use. Visibility may be further restricted by the `guest_view_all_features` project flag (see §5). |

---

## 3. Special / Super Roles

Beyond the three-tier role system, Plane recognises additional elevated authorities:

| Role | Field / Check | Description |
|------|---------------|-------------|
| **Django Superuser** | `User.is_superuser` | Bypasses **all** project-level permission checks (returns `True` unconditionally). Does not bypass workspace-level checks. |
| **Super Admin** | `User.is_super_admin` | When scoped-issue-access is enabled (see §5), super admins see **all** issues regardless of hub filters. |

---

## 4. Backend Permission Classes

### 4.1 Workspace Permission Classes

Defined in `apiserver/plane/app/permissions/workspace.py`:

| Class | Read (GET/HEAD/OPTIONS) | Create (POST) | Update (PUT/PATCH) | Delete (DELETE) |
|-------|------------------------|----------------|---------------------|-----------------|
| **WorkSpaceBasePermission** | Any active member | Anyone (authenticated) | Admin, Member | Admin only |
| **WorkspaceOwnerPermission** | Admin only | Admin only | Admin only | Admin only |
| **WorkSpaceAdminPermission** | Admin, Member | Admin, Member | Admin, Member | Admin, Member |
| **WorkspaceEntityPermission** | Any active member | Admin, Member | Admin, Member | Admin, Member |
| **WorkspaceViewerPermission** | Any active member | Any active member | Any active member | Any active member |
| **WorkspaceUserPermission** | Any active member | Any active member | Any active member | Any active member |

### 4.2 Project Permission Classes

Defined in `apiserver/plane/app/permissions/project.py`:

| Class | Read (GET/HEAD/OPTIONS) | Create (POST) | Update (PUT/PATCH) | Delete (DELETE) |
|-------|------------------------|----------------|---------------------|-----------------|
| **ProjectBasePermission** | Any active workspace member | Admin, Member, Guest (workspace-level) | Project Admin only | Project Admin only |
| **ProjectMemberPermission** | Any active project member | Admin, Member, Guest (workspace-level) | Admin, Member, Guest (project-level) | Admin, Member, Guest (project-level) |
| **ProjectEntityPermission** | Any active project member | Admin, Member, Guest (project-level) | Admin, Member, Guest (project-level) | Admin, Member, Guest (project-level) |
| **ProjectEntityGuestPermission** | Any active project member | Admin, Member, Guest (project-level) | Admin, Member, Guest (project-level) | Admin, Member, Guest (project-level) |
| **ProjectLitePermission** | Any active project member | Any active project member | Any active project member | Any active project member |

### 4.3 Instance Permission Class

Defined in `apiserver/plane/license/api/permissions/instance.py`:

| Class | Requirement |
|-------|-------------|
| **InstanceAdminPermission** | User must be in `InstanceAdmin` with `role >= 15` |

### 4.4 Decorator-Based Permission Check

The `@allow_permission` decorator (`apiserver/plane/app/permissions/base.py`) provides a method-level guard:

```python
@allow_permission([ROLE.ADMIN, ROLE.MEMBER], level="PROJECT")
def some_view(self, request, *args, **kwargs):
    ...
```

- `allowed_roles` — list of `ROLE` enum values that may access this endpoint.
- `level` — `"WORKSPACE"` or `"PROJECT"`.
- `creator` — if `True`, also allows the original creator of the resource (checked via the `model` parameter).

---

## 5. Feature Flags That Affect Permissions

### 5.1 `guest_view_all_features` (Project-level)

- **Field**: `Project.guest_view_all_features` (Boolean)
- **Location**: `apiserver/plane/db/models/project.py`
- When **True**: Guests can view all issues in the project.
- When **False**: Guests only see issues they created or are assigned to.

### 5.2 `scoped_issue_access` (Workspace-level)

- **Field**: `Workspace.scoped_issue_access` (Boolean, default `False`)
- **Location**: `apiserver/plane/db/models/workspace.py`
- When **True**: Issue visibility is restricted based on the user's `hub_codes` / `hub_names` fields. Users only see issues that they created, are assigned to, or that match their hub filters.
- `is_super_admin` users bypass this filter entirely.

---

## 6. User-Level Permission Fields

Defined on the `User` model (`apiserver/plane/db/models/user.py`):

| Field | Type | Description |
|-------|------|-------------|
| `is_superuser` | Boolean | Django built-in. Bypasses all project-level permission checks. |
| `is_super_admin` | Boolean | Plane-specific. Bypasses hub-based scoped-issue-access filtering. |
| `hub_codes` | JSONField (list) | List of hub/department codes used for scoped issue filtering. |
| `hub_names` | JSONField (list) | List of hub/department names used for scoped issue filtering. |
| `employee_permissions` | JSONField (list) | Custom employee-level permission list. |

---

## 7. API Token Authentication

Defined in `apiserver/plane/db/models/api.py` and enforced by `apiserver/plane/api/middleware/api_authentication.py`.

| Token Property | Description |
|----------------|-------------|
| `token` | Unique API key, sent via `X-Api-Key` header. |
| `user_type` | `0` = Human, `1` = Bot. |
| `is_service` | Boolean flag distinguishing service tokens from user tokens. |
| `is_active` | Must be `True` for the token to authenticate. |
| `expired_at` | Optional expiration timestamp. |

An optional `X-Assume-Role` header can be sent alongside the API key for role assumption.

---

## 8. Frontend Permission System

### 8.1 Enums

```typescript
// web/ce/constants/user-permissions/index.ts
enum EUserPermissionsLevel {
  WORKSPACE = "WORKSPACE",
  PROJECT = "PROJECT",
}

enum EUserPermissions {
  ADMIN = 20,
  MEMBER = 15,
  GUEST = 5,
}
```

### 8.2 Permission Matrix Type

```typescript
type TUserAllowedPermissionsObject = {
  create: TUserPermissions[];
  update: TUserPermissions[];
  delete: TUserPermissions[];
  read: TUserPermissions[];
};
```

### 8.3 Default Allowed Permissions

```typescript
const USER_ALLOWED_PERMISSIONS = {
  workspace: {
    dashboard: {
      read: [ADMIN, MEMBER, GUEST],
    },
  },
  project: {},
};
```

### 8.4 Permission Store

The `UserPermissionStore` (`web/core/store/user/permissions.store.ts`) provides:

- `allowPermissions(roles, level)` — checks if the current user has one of the given roles at the specified level.
- `fetchUserWorkspaceInfo()` — retrieves the user's workspace role.
- `fetchUserProjectInfo()` — retrieves the user's project role.

---

## 9. Summary Matrix

| Action | Instance Admin | Workspace Admin | Workspace Member | Workspace Guest | Project Admin | Project Member | Project Guest |
|--------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Configure instance | Yes | — | — | — | — | — | — |
| Delete workspace | — | Yes | No | No | — | — | — |
| Update workspace settings | — | Yes | Yes | No | — | — | — |
| Read workspace data | — | Yes | Yes | Yes | — | — | — |
| Create projects | — | Yes | Yes | Yes | — | — | — |
| Update project settings | — | — | — | — | Yes | No | No |
| Delete project | — | — | — | — | Yes | No | No |
| Create issues / entities | — | — | — | — | Yes | Yes | Conditional |
| Update issues / entities | — | — | — | — | Yes | Yes | Conditional |
| Read all issues | — | — | — | — | Yes | Yes | Conditional* |
| Manage project members | — | — | — | — | Yes | No | No |

\* Guest issue visibility depends on `guest_view_all_features` and `scoped_issue_access` flags.
