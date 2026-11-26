# Issue Type Custom Property Dropdown Integration Technical Plan

## Overview
This document describes the end-to-end changes required to introduce a new `dropdown` custom property data type for issue types. The dropdown behaviour must support both static option lists and remote option sources that are resolved at render time. The solution touches persistence, REST API serializers/views, and the web UI that renders and edits custom property values.

## Goals
- Persist dropdown configuration with each issue-type custom property.
- Expose the configuration through the existing issue type custom property API.
- Render dropdown inputs in `web/core/components/issues/custom-properties.tsx`, sourcing options either from the stored list or from an external API resolved from an identifier. Remote requests must go through a Plane API proxy rather than calling ProjectX directly from the browser.
- Ensure graceful fallback to a text input when remote dependencies cannot supply options (e.g., missing reference number).

## Non-Goals
- Adding multi-select support for dropdown properties.
- Implementing additional remote identifiers beyond `consignmentInvoiceNumber`.
- Refactoring unrelated custom property logic.

## Data Model Updates
The `IssueTypeCustomProperty` model (stored in `apiserver/plane/db/models/issue_type.py`) requires two new nullable fields to describe dropdown configuration:
- `dropdown_source_type`: string flag describing how options are supplied (`custom` vs. `entity`).
- `dropdown_source_field`: JSON field storing either a list of hard-coded options or remote identifiers.

### Migration Plan
1. Generate a new Django migration that adds the two fields with null/blank defaults and updates the model `Meta` if necessary. The migration should also update existing rows by backfilling empty defaults.
2. Confirm migration ordering (next sequential number after the most recent migration in `apiserver/plane/db/migrations`).
3. Run migrations locally to verify schema changes.

## API Layer Changes
The `IssueTypeCustomPropertySerializer` located in `apiserver/plane/api/serializers/issue_type.py` must include the new fields and accept them on create/update.

### Serializer
- Allow both fields to pass through validation (no additional validation required beyond ensuring arrays are serialisable to JSON when `dropdown_source_type === "custom"`).
- Maintain read-only constraints for existing metadata fields.

### Views
`IssueTypeCustomPropertyAPIEndpoint` (see `apiserver/plane/api/views/issue_type.py`) already delegates to the serializer. No behavioural changes are required beyond ensuring request bodies can include the new fields. Confirm the POST endpoint used by `${PLANE_URL}/api/v1/workspaces/${org_id}/issue-type/${issue_type_id}/custom-properties/` passes the data through intact.

### Plane Proxy API for Entity Dropdowns
Introduce a dedicated Plane REST endpoint that proxies entity dropdown lookups to ProjectX so the web client does not make cross-origin requests. The endpoint should:
- Live under the workspace scope (e.g. `GET /api/v1/workspaces/{workspace_id}/issue-type/{issue_type_id}/dropdown-entities/{identifier}/`).
- Validate the requesting user has access to the workspace/issue type before forwarding the request.
- Call the corresponding ProjectX internal API using server-side credentials and return a normalised `{ options: string[] }` payload.
- Surface errors with appropriate status codes so the frontend can fall back to text input when needed.

Add serializer/response typing as required so the handler is easily reusable for new dropdown entities in the future.

### Payload Contract
Clients can send the following shape when `data_type === "dropdown"`:
```json
{
  "name": "Invoice Number",
  "data_type": "dropdown",
  "dropdown_source_type": "custom", // or "entity"
  "dropdown_source_field": ["INV-001", "INV-002"] // or "consignmentInvoiceNumber"
}
```
Responses will echo these values, enabling the web UI to determine option sourcing.

## WB Updates
In Create IssueTypeCustomProperties api called from ticket master workflows (create ticket master and update ticket master) - 
Add dropdownSourceType and dropdownSourceField in the payload

## Frontend Updates
All dropdown rendering logic lives inside `web/core/components/issues/custom-properties.tsx`. Current inputs are keyed by `data_type` and only cover `date`, `boolean`, `number`, and `text`. The component must:

1. Accept `dropdownSourceType` and `dropdownSourceField` values from the API payload alongside existing property data.
2. Build an options cache for dropdowns, sourcing values via the rules below.
3. Render a `<select>` control when options are available; otherwise fall back to a plain text `<Input>` to allow manual entry.

### State Mapping
Augment the `mergedCustomProperties` mapping so each property includes `dropdown_source_type` and `dropdown_source_field` (matching backend casing) for downstream logic.

### Option Resolution
Implement a helper (e.g., `useDropdownOptions(properties, dependencies)`) that constructs an options map:
- **Custom Source**: when `dropdown_source_type === "custom"`, normalise `dropdown_source_field` into a string array and convert to `{ label, value }` pairs.
- **Entity/API Source**: resolve `dropdown_source_field` to a single identifier string (e.g., `consignmentInvoiceNumber`), look it up inside a `customPropertyDropdownEntityAPIMap`, and call the corresponding async function. Provide the function with the issue context required by the API (issue `entityData`, `userId`, `organisationId`, `accessToken`, `source`). Cache the results to avoid duplicate requests. Each fetcher must invoke the new Plane proxy API rather than contacting ProjectX directly from the browser.
- **Error Handling**: if an identifier has no handler, or the handler rejects (for example because the issue lacks a `reference_number`), default the options array to `[]` and log a warning.

### Rendering
Add a `dropdown` entry to `inputComponents` that:
- Displays a `<select>` with a placeholder when the options array is non-empty.
- Disables multi-select capability.
- Calls `handleChange`/`handleBlur` handlers already defined for other inputs.
If the dropdown options array is empty (because the API could not supply values), render the text input fallback to keep the property editable.

### Remote Option Fetcher Example
Define `fetchConsignmentInvoice` inside an appropriate shared utilities module if not already present. The function should:
- Verify that `entityData.reference_number` (consignment number) is populated.
- Call the new Plane proxy endpoint (e.g., `GET ${PLANE_URL}/api/v1/workspaces/${workspace_id}/issue-type/${issue_type_id}/dropdown-entities/consignmentInvoiceNumber/`) with the user's auth token so the server performs the ProjectX lookup.
- Return an array of invoice numbers (strings). On failure, return an empty array.
- Extend the API in the ProjectX repository so the Plane proxy can reach `${PX_BASE_URL}/api/internal/consignment-invoice/fetch` using server-side credentials. This ensures internal consumers can reuse the same contract without exposing PX credentials to the browser.

Register this fetcher in `customPropertyDropdownEntityAPIMap` so the dropdown renderer can call it when encountering the `consignmentInvoiceNumber` identifier.

## Edge Cases & Fallbacks
- Ensure non-dropdown properties continue to function unchanged (dropdown fields should default to `null`/`[]` when persisted).
- Protect against malformed `dropdown_source_field` values (e.g., number or object) by coercing to an array/string safely.
- When issue metadata required by the remote fetcher is missing, display a user-facing hint or fallback to text input to prevent blocking edits.

## Testing Strategy
1. **Backend Unit Tests**
   - Extend serializer tests to confirm the new fields are accepted and returned.
   - Add migration test coverage if the project uses schema snapshot testing.

2. **API Integration Tests**
   - POST a dropdown custom property with `dropdown_source_type = custom` and ensure the stored/retrieved values match.
   - POST another property with `dropdown_source_type = entity` and ensure the identifier persists.

3. **Frontend Unit/Component Tests**
   - Mock API responses in `custom-properties.tsx` to verify custom source arrays render as options.
   - Mock the entity fetcher to ensure async option loading updates the UI and handles empty responses.

4. **Manual QA**
   - Create dropdown custom properties via the UI/API in both modes.
   - Load an issue whose `reference_number` exists and confirm dropdown options populate from the remote API.
   - Load an issue without `reference_number` to observe the text input fallback.

## Deployment Considerations
- Coordinate backend and frontend deployments so the UI does not request fields before the API exposes them.
- Communicate the new payload contract to any integrators using the custom property endpoint.
- Ensure environment variables required by remote fetchers (e.g., `API_BASE_URL`) are configured.

## Rollback Plan
- If problems occur, remove the new dropdown fields from the serializer and revert the migration (rolling back the database schema). Ensure data migrations are reversible.
- Feature-flagging is not required but could be considered if remote identifiers will expand in future iterations.
