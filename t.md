# Technical Specification: Dropdown Custom Properties

## 1. Executive Summary

### 1.1 Purpose

This document specifies the technical implementation for adding dropdown support to Issue Type Custom Properties in Plane. The feature enables dynamic dropdown fields with values fetched from WB (n8n workflow) at runtime, with WB acting as a router to external systems like PX (ProjectX).

### 1.2 System Architecture Overview

**Four-Layer Architecture**:

```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│   Frontend  │─────►│    Plane    │─────►│  WB (n8n)   │─────►│  PX (API)   │
│   (React)   │◄─────│   Backend   │◄─────│  Workflows  │◄─────│  External   │
└─────────────┘      └─────────────┘      └─────────────┘      └─────────────┘
      │                     │                     │                     │
   Browser            Simple Proxy         Smart Router          Data Source
   Renders UI         Validates &          Type Detection        Business Data
   GET requests       Forwards             Calls PX API          Invoices, etc.
```

**Key Architectural Decisions**:
- ✅ **Unified API**: Single endpoint for both custom and system dropdown types
- ✅ **Simple Proxy**: Plane backend has no business logic, just forwards requests
- ✅ **Smart Router**: WB (n8n) handles all type determination and routing
- ✅ **External Data**: PX provides business data via internal APIs (not direct DB queries)
- ✅ **No Migrations**: Uses existing JSONB `value` field for configuration

### 1.3 Scope

**In Scope**:
- Dropdown data type for custom properties
- Two dropdown variants: Custom and System
- Real-time value fetching from WB
- WB integration with PX internal APIs
- WB ticket master workflow updates
- Frontend dropdown rendering
- Error handling and fallback mechanisms
- Cross-system logging and monitoring

**Out of Scope**:
- Multi-select dropdowns
- Client-side value caching
- Offline dropdown support
- Database schema changes (uses existing fields)

### 1.4 Key Benefits

| Benefit | Description |
|---------|-------------|
| **Dynamic Data** | Values fetched in real-time from external systems |
| **Zero Schema Changes** | Uses existing database fields |
| **Flexible** | Supports both global and context-specific dropdowns |
| **Resilient** | Graceful fallback to text input on failures |
| **Scalable** | Easy to add new dropdown types via WB configuration |
| **Decoupled** | Plane remains simple, complexity in WB layer |

### 1.5 Success Criteria

- [ ] Users can create dropdown custom properties
- [ ] Dropdowns fetch values from WB at render time
- [ ] System type dropdowns use issue context (reference_number)
- [ ] Graceful fallback when WB unavailable
- [ ] Response time < 500ms for 95% of requests
- [ ] Zero database migrations required
- [ ] PX internal API integrated with WB
- [ ] WB ticket master workflows updated

### 1.6 System Responsibilities Summary

| System | Team | Responsibilities | Changes Required |
|--------|------|------------------|------------------|
| **Frontend (React)** | Plane Frontend | - Render dropdowns<br>- Make GET requests<br>- Handle loading/error states<br>- Fallback to text input | - Update custom-properties.tsx- Build query parameters |
| **Plane Backend (Django)** | Plane Backend | - **Simple Proxy Only**<br>- Validate workspace<br>- Forward to WB<br>- Return response | - Create DropdownOptionsAPIEndpoint<br>- Add WB_BASE_URL config<br>- 10s timeout logic |
| **WB (n8n)** | Workflow Team | - **Smart Router**<br>- Determine custom vs system<br>- Route to correct handler<br>- Call PX API for system types<br>- Format responses | - Update `/webhook/fetch-dropdown-values`<br>- Update ticket master workflows<br>- Add PX credentials<br>- Configure identifier routing |
| **PX (ProjectX)** | PX Team | - **Data Source**<br>- Provide internal APIs<br>- Return business data<br>- Handle queries efficiently | - Create `/api/internal/consignment-invoice/fetch`<br>- Implement query logic<br>- Return standardized format |

---

## 2. Background & Requirements

### 2.1 Problem Statement

Currently, custom properties only support fixed input types (text, number, boolean, date). Users need dropdown fields with:
1. Dynamic values from external systems
2. Issue-specific options based on context
3. Real-time data freshness

### 2.2 Business Requirements

**BR-001**: Support dropdown as a new custom property data type  
**BR-002**: Enable two dropdown types: Custom (global) and System (contextual)  
**BR-003**: Fetch dropdown values from WB (n8n) at runtime  
**BR-004**: Display dropdowns in issue forms  
**BR-005**: Fallback to text input if values unavailable  

### 2.3 Technical Requirements

**TR-001**: Use existing database schema (no migrations)  
**TR-002**: Follow Plane's webhook integration patterns  
**TR-003**: Session-based authentication for frontend  
**TR-004**: Bearer token authentication for WB  
**TR-005**: 10-second timeout for WB calls  
**TR-006**: Return 200 OK with empty options on errors  

### 2.4 Constraints

- Must use existing `value` JSONB field
- No new database columns
- Must work with current Plane authentication
- Must integrate with existing WB infrastructure
- Frontend must support graceful degradation

## 3. Solution Architecture

### 3.1 System Context

```
┌─────────────────────────────────────────────────────────────┐
│                         Plane System                         │
│                                                              │
│  ┌──────────────┐       ┌──────────────┐                     │
│  │   Frontend   │◄─────►│   Backend    │                     │
│  │  (React)     │       │  (Django)    │                     │
│  └──────────────┘       └───────┬──────┘                     │
│                                  │                           │
└──────────────────────────────────┼───────────────────────────┘
                                   │
                                   │ HTTPS (Proxy)
                                   ↓
                         ┌──────────────────┐
                         │   WB (n8n)       │
                         │   Workflows      │
                         └────────┬─────────┘
                                  │
                                  │ API Call (HTTPS)
                                  ↓
                         ┌──────────────────┐
                         │   PX API         │
                         │   (External)     │
                         └──────────────────┘
```

### 3.2 Component Architecture

**Frontend Components**:
- `CustomProperties.tsx` - Dropdown rendering
- State management for dropdown options
- Loading states and error handling
- Axios HTTP client for API calls

**Backend Components**:
- `DropdownOptionsAPIEndpoint` - Proxy endpoint (Plane → WB)
- Request validation and formatting
- WB integration logic
- Django Sessions authentication

**External Systems**:
- **WB (n8n)** - Workflow automation platform
  - Handles dropdown type routing
  - Manages ticket master workflows
  - Proxies requests to PX
- **PX (ProjectX)** - External system
  - Provides business data (invoices, consignments, etc.)
  - Exposes internal APIs for data retrieval
  - Called by WB, not directly by Plane

### 3.3 Technology Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | React, TypeScript, Axios | UI rendering, API calls |
| Backend | Django, Python, Requests | API endpoint, WB proxy |
| Integration | n8n (WB) | Workflow automation |
| Database | PostgreSQL | Data persistence |
| Authentication | Django Sessions, Bearer Token | Security |

---

## 4. Technical Design

### 4.1 Data Model

**No schema changes required**. Configuration stored in existing `value` field:

```sql
-- Existing table: issue_type_custom_properties
-- Existing columns used:
--   - data_type: VARCHAR(255)  → "dropdown"
--   - value: JSONB              → Stores dropdown config
```

**Dropdown Configuration Structure**:
```json
{
  "dropdown_source_type": "custom" | "system",
  "dropdown_source_field": "identifier_string"
}
```

### 4.2 Dropdown Types

#### 4.2.1 Custom Type

**Characteristics**:
- Global dropdown values
- Same options for all issues
- No issue context required

**Configuration Example**:
```json
{
  "dropdown_source_type": "custom",
  "dropdown_source_field": "priorityLevels"
}
```

**WB Request**:
```json
{
  "issue_type_id": "uuid",
  "issue_type_custom_property_id": "uuid",
  "custom_property_id": "uuid",
  "workspace_id": "uuid"
}
```

**WB Response**:
```json
{
  "issue_type_id": "uuid",
  "data": {
    "values": ["High", "Medium", "Low", "Critical"]
  }
}
```

#### 4.2.2 System Type

**Characteristics**:
- Issue-specific values
- Requires issue context (reference_number)
- Queries external systems

**Configuration Example**:
```json
{
  "dropdown_source_type": "system",
  "dropdown_source_field": "consignmentInvoiceNumber"
}
```

**WB Request**:
```json
{
  "issue_type_id": "uuid",
  "issue_type_custom_property_id": "uuid",
  "custom_property_id": "uuid",
  "reference_number": "CN12345",
  "workspace_id": "uuid"
}
```

**WB Response**:
```json
{
  "issue_type_id": "uuid",
  "data": {
    "records": [
      {"invoice_number": "INV-001", "invoice_date": "2025-10-15"},
      {"invoice_number": "INV-002", "invoice_date": "2025-10-16"}
    ]
  }
}
```

### 4.3 Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **Use existing fields** | Avoid migrations, faster deployment |
| **Fetch at render time** | Ensures data freshness |
| **10s timeout** | Balance between UX and reliability |
| **Graceful fallback** | Don't block user workflow |
| **200 OK on errors** | Enable frontend fallback logic |

---
Plane Proxy API for Entity Dropdowns
Introduce a dedicated Plane REST endpoint that proxies entity dropdown lookups to ProjectX so the web client does not make cross-origin requests. The endpoint should:

Live under the workspace scope (e.g. GET /api/v1/workspaces/{workspace_id}/issue/{issue_type_id}/dropdown-entities/{identifier}/).

Validate the requesting user has access to the workspace/issue type before forwarding the request.
Call the corresponding ProjectX internal API using server-side credentials and return a normalised { options: string[] } payload.
Surface errors with appropriate status codes so the frontend can fall back to text input when needed.
Add serializer/response typing as required so the handler is easily reusable for new dropdown entities in the future.



## 5. Implementation Specifications

### 5.1 Backend Implementation

#### 5.1.1 New API Endpoint

**File**: `apiserver/plane/api/views/issue_type.py`

**Class**: `DropdownOptionsAPIEndpoint`

**Method**: `GET`

**Purpose**: Proxy dropdown value requests to WB

**Key Logic**:
1. Validate workspace access
2. Extract identifier from URL path
3. Pull `issue_type_id`, `issue_type_custom_property_id`, and `custom_property_id` from query parameters
4. Optionally read `reference_number` from query parameters (for system types)
5. Build WB request payload with all relevant fields
6. Call WB with 10s timeout (WB handles all segregation logic)
7. Parse WB response
8. Return formatted options

**Note**: All logic for custom vs system type, identifier mapping, and data segregation is handled by n8n, not by the Plane backend.

**Error Handling**:
- Workspace not found → 404
- Missing required query parameters → 400
- WB timeout → 200 with empty options
- WB error → 200 with empty options
- Network error → 200 with empty options

#### 5.1.2 URL Routing

**File**: `apiserver/plane/api/urls/issue_type.py`

**New Route**:
```python
path(
    "workspaces/<str:slug>/issue/dropdown-options/<str:identifier>/",
    DropdownOptionsAPIEndpoint.as_view(),
    name="dropdown-options",
)
```

**URL Pattern**: `/api/workspaces/{slug}/issue/dropdown-options/{identifier}/`

**Note**: All identifiers are sent as query parameters to keep the endpoint idempotent and compatible with GET semantics.

#### 5.1.3 WB Integration

**Purpose**: Single unified endpoint to WB

**WB Endpoint**: `/webhook/fetch-dropdown-values` (single endpoint for all dropdown types)

**Plane Backend Role**: 
- Simple proxy - forwards all data to WB
- No identifier mapping required
- No custom vs system type logic
- WB handles all segregation and routing

**Adding New Dropdown Types**:
1. Configure in n8n workflow
2. Update n8n to handle new identifier
3. No Plane backend changes required

### 5.2 Frontend Implementation

#### 5.2.1 Component Changes

**File**: `web/core/components/issues/custom-properties.tsx`

**Changes Required**:
1. Add `issueData` prop (contains reference_number)
2. Add state for dropdown options
3. Add state for loading indicators
4. Add dropdown options loading logic
5. Parse dropdown config from value field
6. Add dropdown input component
7. Handle loading, error, and empty states

#### 5.2.2 State Management

**New State Variables**:
```typescript
const [dropdownOptions, setDropdownOptions] = useState<
  Record<string, { value: string; label: string }[]>
>({});

const [loadingDropdowns, setLoadingDropdowns] = useState<
  Record<string, boolean>
>({});
```

#### 5.2.3 Dropdown Loading Logic

**Trigger**: When `issueTypeCustomProperties` changes

**For Each Property**:
1. Check if `data_type === "dropdown"`
2. Parse dropdown config from `value` field
3. Extract identifier from `dropdown_source_field`
4. Determine if custom or system type
5. Build query parameters (`issue_type_id`, `issue_type_custom_property_id`, `custom_property_id`, and `reference_number` for system types)
6. Set loading state
7. Call `GET /dropdown-options/{identifier}/?query_params`
8. Parse response and format options
9. Update dropdown options state
10. Clear loading state

#### 5.2.4 Rendering Logic

**States**:
- **Loading**: Show disabled select with "Loading options..."
- **Has Options**: Show select dropdown with options
- **No Options**: Show text input (fallback)

**Dropdown HTML**:
```html
<select value={value} onChange={handleChange} onBlur={handleBlur}>
  <option value="">Select {property.key}</option>
  {options.map(opt => (
    <option key={opt.value} value={opt.value}>{opt.label}</option>
  ))}
</select>
```

### 5.3 Configuration

#### 5.3.1 Environment Variables

**File**: `.env` or environment configuration

**Required**:
```bash
WB_BASE_URL=https://your-n8n-instance.com
```

**Optional**:
```bash
WB_API_KEY=your_api_key_for_authentication
```

#### 5.3.2 WB Workflows

**Single Unified Workflow**:

**Fetch Dropdown Values** (Handles both Custom and System types)
   - Endpoint: `/webhook/fetch-dropdown-values`
   - Input: `{issue_type_id, issue_type_custom_property_id, custom_property_id, identifier, workspace_id, reference_number (optional)}`
   - Logic: 
     - Determines custom vs system based on identifier
     - For system types: Calls PX API with reference_number
     - For custom types: Returns predefined values
   - Output: Standardized format for both types

### 5.4 WB (n8n) Updates for Ticket Master Workflows

**Location**: WB workflows - Create Ticket Master & Update Ticket Master

**Required Changes**:

When calling the Plane API to create or update IssueTypeCustomProperty, include the dropdown configuration fields in the payload.

**Updated Payload Structure**:

```json
{
  "name": "Invoice Number",
  "data_type": "dropdown",
  "value": {
    "dropdown_source_type": "system",
    "dropdown_source_field": "consignmentInvoiceNumber"
  },
  "is_active": true,
  "is_required": false
}
```

**Workflows to Update**:

1. **Create Ticket Master Workflow**
   - When creating custom properties with type "dropdown"
   - Add `dropdown_source_type` and `dropdown_source_field` inside the `value` object
   - Map from ticket master configuration to Plane API format

2. **Update Ticket Master Workflow**
   - When updating existing dropdown custom properties
   - Preserve or update dropdown configuration as needed
   - Handle migration of old properties if needed

**Field Mapping**:

| Ticket Master Field | Plane API Field | Location |
|---------------------|-----------------|----------|
| `dropdownSourceType` | `dropdown_source_type` | Inside `value` JSONB |
| `dropdownSourceField` | `dropdown_source_field` | Inside `value` JSONB |
| `dataType: "dropdown"` | `data_type: "dropdown"` | Top-level field |

### 5.5 PX (ProjectX) Integration

**Purpose**: PX provides the actual business data for system-type dropdowns.

**Architecture**:

```
Plane Frontend
    ↓
    GET /api/.../dropdown-options/consignmentInvoiceNumber/?reference_number=CN12345
    ↓
Plane Backend (Proxy)
    ↓
    POST to WB /webhook/fetch-dropdown-values
    {
      "issue_type_id": "...",
      "reference_number": "CN12345",
      ...
    }
    ↓
WB (n8n) - Type Router
    ↓
    Identifies as system type
    ↓
    POST to PX API /api/internal/consignment-invoice/fetch
    {
      "consignment_number": "CN12345",
      "user_id": "...",
      "workspace_id": "..."
    }
    ↓
PX Internal API
    ↓
    Queries PX database
    ↓
    Returns invoice data
    {
      "invoices": [
        {"invoice_number": "INV-001", "invoice_date": "2025-10-15"},
        {"invoice_number": "INV-002", "invoice_date": "2025-10-16"}
      ]
    }
    ↓
WB (n8n)
    ↓
    Formats response for Plane
    {
      "data": {
        "records": [
          {"invoice_number": "INV-001"},
          {"invoice_number": "INV-002"}
        ]
      }
    }
    ↓
Plane Backend
    ↓
    Extracts invoice_numbers
    ↓
    Returns {"options": ["INV-001", "INV-002"]}
    ↓
Frontend renders dropdown
```

#### 5.5.1 PX API Requirements

**New Internal API Endpoint**:

**Endpoint**: `POST /api/internal/consignment-invoice/fetch`

**Authentication**: Server-to-server (WB credentials)

**Request**:
```json
{
  "consignment_number": "CN12345",
  "user_id": "optional-uuid",
  "workspace_id": "optional-uuid"
}
```

**Response**:
```json
{
  "success": true,
  "invoices": [
    {
      "invoice_number": "INV-001",
      "invoice_date": "2025-10-15",
      "amount": 1000.00,
      "currency": "USD"
    },
    {
      "invoice_number": "INV-002",
      "invoice_date": "2025-10-16",
      "amount": 1500.00,
      "currency": "USD"
    }
  ]
}
```

**Error Response**:
```json
{
  "success": false,
  "error": "Consignment not found",
  "code": "CONSIGNMENT_NOT_FOUND"
}
```

#### 5.5.2 PX Security Considerations

**Authentication**:
- WB authenticates to PX using server-side credentials
- No direct browser-to-PX calls
- Credentials stored securely in WB environment

**Authorization**:
- PX may optionally validate workspace_id
- PX may implement rate limiting
- PX logs all internal API calls for audit

**Data Privacy**:
- Only necessary fields returned (invoice numbers)
- Sensitive financial data can be filtered
- PX respects data access policies

#### 5.5.3 Adding New PX Identifiers

To add a new system-type dropdown (e.g., "customerOrders"):

1. **PX Side**:
   - Create new internal API endpoint: `/api/internal/customer-orders/fetch`
   - Implement query logic
   - Return standardized format

2. **WB Side**:
   - Update `/webhook/fetch-dropdown-values` workflow
   - Add routing for new identifier
   - Map to new PX endpoint
   - Format response

3. **Plane Side**:
   - No changes needed (simple proxy)

4. **Frontend Side**:
   - Use same component
   - Pass new identifier
   - No code changes needed

---

## 6. API Specifications

### 6.1 Create Dropdown Property

**Endpoint**: `POST /api/workspaces/{slug}/issue-type/{issue_type_id}/custom-properties/`

**Authentication**: Session-based (existing)

**Request Headers**:
```
Content-Type: application/json
Cookie: sessionid=...
```

**Request Body (Custom Type)**:
```json
{
  "name": "Priority Level",
  "data_type": "dropdown",
  "value": {
    "dropdown_source_type": "custom",
    "dropdown_source_field": "priorityLevels"
  },
  "is_active": true,
  "is_required": false
}
```

**Request Body (System Type)**:
```json
{
  "name": "Invoice Number",
  "data_type": "dropdown",
  "value": {
    "dropdown_source_type": "system",
    "dropdown_source_field": "consignmentInvoiceNumber"
  },
  "is_active": true,
  "is_required": false
}
```

**Response**: `201 Created`
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Priority Level",
  "data_type": "dropdown",
  "value": {
    "dropdown_source_type": "custom",
    "dropdown_source_field": "priorityLevels"
  },
  "is_active": true,
  "is_required": false,
  "issue_type": "650e8400-e29b-41d4-a716-446655440000",
  "created_at": "2025-10-17T10:00:00Z",
  "updated_at": "2025-10-17T10:00:00Z"
}
```

### 6.2 Fetch Dropdown Options

**Endpoint**: `GET /api/workspaces/{slug}/issue/dropdown-options/{identifier}/`

**Note**: This is a **SINGLE UNIFIED ENDPOINT** for both custom and system types. The same API call and same base parameters are used for both types.

**Authentication**: Session-based (existing)

**Path Parameters**:
- `slug` (string): Workspace slug
- `identifier` (string): Dropdown identifier

**Query Parameters** (Always Required):
- `issue_type_id` (uuid): Issue type ID
- `issue_type_custom_property_id` (uuid): Custom property ID
- `custom_property_id` (uuid): Custom property definition ID
- `reference_number` (string, optional): Issue reference number - only used for system types, ignored for custom types

**Request Headers**:
```
Cookie: sessionid=...
```

**Example Request (Custom Type)**:
```
GET /api/workspaces/acme/issue/dropdown-options/priorityLevels/?issue_type_id=550e8400-e29b-41d4-a716-446655440000&issue_type_custom_property_id=650e8400-e29b-41d4-a716-446655440000&custom_property_id=750e8400-e29b-41d4-a716-446655440000
```

**Example Request (System Type)**:
```
GET /api/workspaces/acme/issue/dropdown-options/consignmentInvoiceNumber/?issue_type_id=550e8400-e29b-41d4-a716-446655440000&issue_type_custom_property_id=650e8400-e29b-41d4-a716-446655440000&custom_property_id=750e8400-e29b-41d4-a716-446655440000&reference_number=CN12345
```

**Key Points**:
- ✅ Same endpoint for both types
- ✅ Same required parameters (`issue_type_id`, `issue_type_custom_property_id`, `custom_property_id`) for both
- ✅ `reference_number` is optional - only provided for system types
- ✅ n8n determines the type based on identifier or custom property configuration
- ✅ Plane backend is a simple proxy - no type logic

**Success Response**: `200 OK`
```json
{
  "options": [
    {"value": "High", "label": "High"},
    {"value": "Medium", "label": "Medium"},
    {"value": "Low", "label": "Low"},
    {"value": "Critical", "label": "Critical"}
  ]
}
```

**Error Response** (Graceful): `200 OK`
```json
{
  "options": [],
  "error": "reference_number required"
}
```

**Error Response** (Fatal): `400 Bad Request`
```json
{
  "error": "Unknown identifier: invalidIdentifier"
}
```

**Error Response** (Not Found): `404 Not Found`
```json
{
  "error": "Workspace not found"
}
```

### 6.3 WB API Contract

#### 6.3.1 Request to WB

**Endpoint**: `POST {WB_BASE_URL}/webhook/fetch-dropdown-values` (single unified endpoint)

**Headers**:
```
Content-Type: application/json
User-Agent: Plane-API
Authorization: Bearer {WB_API_KEY}  (if configured)
```

**Body (Custom Type)**:
```json
{
  "issue_type_id": "550e8400-e29b-41d4-a716-446655440000",
  "issue_type_custom_property_id": "650e8400-e29b-41d4-a716-446655440000",
  "custom_property_id": "750e8400-e29b-41d4-a716-446655440000",
  "identifier": "priorityLevels",
  "workspace_id": "650e8400-e29b-41d4-a716-446655440000"
}
```

**Body (System Type - With Reference)**:
```json
{
  "issue_type_id": "550e8400-e29b-41d4-a716-446655440000",
  "issue_type_custom_property_id": "650e8400-e29b-41d4-a716-446655440000",
  "custom_property_id": "750e8400-e29b-41d4-a716-446655440000",
  "identifier": "consignmentInvoiceNumber",
  "reference_number": "CN12345",
  "workspace_id": "650e8400-e29b-41d4-a716-446655440000"
}
```

**Note**: n8n (WB) determines the type (custom vs system) based on the identifier and handles all segregation logic internally. For system types, n8n calls PX APIs (not direct database queries).

#### 6.3.2 Response from WB

**Custom Type Response**:
```json
{
  "issue_type_id": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "values": ["High", "Medium", "Low", "Critical"]
  }
}
```

**System Type Response**:
```json
{
  "issue_type_id": "550e8400-e29b-41d4-a716-446655440000",
  "data": {
    "records": [
      {
        "invoice_number": "INV-001",
        "invoice_date": "2025-10-15",
        "amount": 1000.00
      },
      {
        "invoice_number": "INV-002",
        "invoice_date": "2025-10-16",
        "amount": 1500.00
      }
    ]
  }
}
```

---

## 7. Data Flow

### 7.1 Create Dropdown Property Flow

```
Admin/User
    ↓
    POST /custom-properties/
    {
      "data_type": "dropdown",
      "value": {
        "dropdown_source_type": "custom",
        "dropdown_source_field": "priorityLevels"
      }
    }
    ↓
Plane Backend
    ↓
    Validates request
    ↓
    Stores in database
    value = {"dropdown_source_type": "custom", "dropdown_source_field": "priorityLevels"}
    ↓
    Returns 201 Created
    ↓
User receives confirmation
```

### 7.2 Render Dropdown Flow (Custom Type)

```
User Opens Issue
    ↓
Frontend Loads Custom Properties
    ↓
Frontend: data_type === "dropdown"
    ↓
Frontend: Parses value field
    dropdown_source_type = "custom"
    dropdown_source_field = "priorityLevels"
    ↓
Frontend: GET /issue/dropdown-options/priorityLevels/
    Query Params: ?issue_type_id=uuid&issue_type_custom_property_id=uuid&custom_property_id=uuid
    ↓
Plane Backend
    ↓
    Validates workspace access
    ↓
    Proxies request to WB (no segregation logic)
    ↓
    POST {WB_BASE_URL}/webhook/fetch-dropdown-values
    {
      "issue_type_id": "uuid",
      "issue_type_custom_property_id": "uuid",
      "custom_property_id": "uuid",
      "identifier": "priorityLevels",
      "workspace_id": "uuid"
    }
    ↓
WB (n8n)
    ↓
    Identifies as custom type based on identifier
    ↓
    Returns: {"data": {"values": ["High", "Medium", "Low"]}}
    ↓
Plane Backend
    ↓
    Normalizes values to option list
    ↓
    Returns: {"options": [{"value": "High", "label": "High"}, ...]}
    ↓
Frontend
    ↓
    Updates state
    ↓
    Renders <select> with options
    ↓
User Sees Dropdown
```

### 7.3 Render Dropdown Flow (System Type)

```
User Opens Issue (reference_number = "CN12345")
    ↓
Frontend Loads Custom Properties
    ↓
Frontend: data_type === "dropdown"
    ↓
Frontend: Parses value field
    dropdown_source_type = "system"
    dropdown_source_field = "consignmentInvoiceNumber"
    ↓
Frontend: GET /issue/dropdown-options/consignmentInvoiceNumber/
    Query Params: ?issue_type_id=uuid&issue_type_custom_property_id=uuid&custom_property_id=uuid&reference_number=CN12345
    ↓
Plane Backend
    ↓
    Validates workspace access
    ↓
    Proxies request to WB (no segregation logic)
    ↓
    POST {WB_BASE_URL}/webhook/fetch-dropdown-values
    {
      "issue_type_id": "uuid",
      "issue_type_custom_property_id": "uuid",
      "custom_property_id": "uuid",
      "identifier": "consignmentInvoiceNumber",
      "reference_number": "CN12345",
      "workspace_id": "uuid"
    }
    ↓
WB (n8n)
    ↓
    Identifies as system type based on identifier
    ↓
    Calls PX API with CN12345 (not direct DB query)
    ↓
    Returns: {
      "data": {
        "records": [
          {"invoice_number": "INV-001"},
          {"invoice_number": "INV-002"}
        ]
      }
    }
    ↓
Plane Backend
    ↓
    Extracts invoice_numbers
    ↓
    Returns: {"options": [{"value": "INV-001", "label": "INV-001"}, {"value": "INV-002", "label": "INV-002"}]}
    ↓
Frontend
    ↓
    Updates state
    ↓
    Renders <select> with options
    ↓
User Sees Issue-Specific Dropdown
```

### 7.4 Error Flow

```
User Opens Issue
    ↓
Frontend: GET /issue/dropdown-options/identifier/
    Query Params: ?issue_type_id=uuid&issue_type_custom_property_id=uuid&custom_property_id=uuid
    ↓
Plane Backend
    ↓
    POST to WB (simple proxy)
    ↓
WB Timeout / Error
    ↓
Plane Backend
    ↓
    Catches exception
    ↓
    Returns: 200 OK {"options": [], "error": "..."}
    ↓
Frontend
    ↓
    Receives empty options
    ↓
    Renders <input type="text"> (fallback)
    ↓
User Can Still Edit Field Manually
```

---

## 8. Testing Strategy

### 8.1 Unit Tests

#### 8.1.1 Backend Tests

**File**: `apiserver/plane/tests/test_dropdown_custom_properties.py`

**Test Cases**:

1. **test_custom_dropdown_success**
   - Mock WB response with values
   - Call endpoint with custom identifier
   - Assert WB called with correct payload
   - Assert options returned correctly

2. **test_system_dropdown_success**
   - Mock WB response with records
   - Call endpoint with system identifier and reference_number
   - Assert WB called with context
   - Assert options extracted correctly

3. **test_missing_reference_number**
   - Call system endpoint without reference_number
   - Assert returns empty options with error

4. **test_wb_timeout**
   - Mock `requests.Timeout` exception
   - Assert returns 200 with empty options

5. **test_invalid_identifier**
   - Call with unknown identifier
   - Assert returns 400 Bad Request

6. **test_workspace_not_found**
   - Call with invalid workspace slug
   - Assert returns 404 Not Found

#### 8.1.2 Frontend Tests

**File**: `web/core/components/issues/__tests__/custom-properties.test.tsx`

**Test Cases**:

1. **test_custom_dropdown_rendering**
   - Mock property with custom type
   - Mock API response
   - Assert dropdown renders with options

2. **test_system_dropdown_rendering**
   - Mock property with system type
   - Mock API response
   - Assert API called with reference_number
   - Assert dropdown renders

3. **test_loading_state**
   - Mock delayed API response
   - Assert "Loading options..." shown

4. **test_fallback_to_text_input**
   - Mock empty options response
   - Assert text input rendered

5. **test_error_handling**
   - Mock API error
   - Assert text input fallback

### 8.2 Integration Tests

**Scenarios**:

1. **End-to-End Custom Dropdown**
   - Create custom property via API
   - Load issue in frontend
   - Verify dropdown loads and displays
   - Select value and save
   - Verify value persisted

2. **End-to-End System Dropdown**
   - Create system property via API
   - Load issue with reference_number
   - Verify dropdown loads with context
   - Verify correct values displayed

3. **WB Integration**
   - Test actual WB calls (integration environment)
   - Verify request format
   - Verify response parsing

### 8.3 Performance Tests

**Scenarios**:

1. **Response Time**
   - Measure P50, P95, P99 response times
   - Target: P95 < 500ms

2. **Concurrent Requests**
   - 100 concurrent dropdown option requests
   - Measure success rate and response times

3. **WB Timeout Handling**
   - Simulate WB delays
   - Verify 10s timeout works
   - Verify graceful fallback

### 8.4 User Acceptance Testing

Coordinate UAT with product stakeholders to validate user experience across both dropdown types and fallback scenarios.

---

## 9. Deployment Plan

### 9.1 Pre-Deployment Checklist

**Infrastructure**:
- [ ] `WB_BASE_URL` configured in all environments
- [ ] `WB_API_KEY` configured (if required)
- [ ] WB workflows deployed and tested
- [ ] Network connectivity verified (Plane ↔ WB ↔ PX)
- [ ] PX internal API endpoints deployed
- [ ] PX credentials configured in WB

**Code**:
- [ ] Backend changes reviewed and approved
- [ ] Frontend changes reviewed and approved
- [ ] Unit tests passing (100% coverage)
- [ ] Integration tests passing
- [ ] No linter errors

**Documentation**:
- [ ] Technical documentation complete
- [ ] API documentation updated
- [ ] README updated
- [ ] Changelog updated

**External Systems**:
- [ ] PX internal API deployed (`/api/internal/consignment-invoice/fetch`)
- [ ] WB ticket master workflows updated (Create & Update)
- [ ] WB routing logic configured for identifiers
- [ ] Cross-system credentials validated

### 9.2 Deployment Steps

#### 9.2.1 Staging Deployment

**Day 1 - External Systems (PX & WB)**:
1. Deploy PX internal API endpoints to staging
   - `/api/internal/consignment-invoice/fetch`
   - Verify endpoints with direct API calls
2. Deploy WB workflows to staging
   - Update ticket master workflows (Create & Update)
   - Configure `/webhook/fetch-dropdown-values` routing
   - Add PX credentials to WB environment
3. Test WB → PX connectivity
   - Call WB endpoint with test data
   - Verify PX response format
4. Test WB routing logic
   - Test custom type identifier
   - Test system type identifier

**Day 2 - Plane Backend**:
1. Deploy backend changes to staging
2. Restart Django application servers
3. Add `WB_BASE_URL` and `WB_API_KEY` to environment
4. Verify `/dropdown-options/` endpoint accessible
5. Test Plane → WB integration with curl/Postman
6. Verify timeout handling (mock WB delay)

**Day 3 - Plane Frontend**:
1. Deploy frontend changes to staging
2. Clear CDN cache
3. Verify component renders correctly
4. Test dropdown loading (both types)
5. Test error scenarios (missing reference_number, WB timeout)
6. Test fallback to text input

**Day 4 - Integration Testing**:
1. Full end-to-end testing (Frontend → Plane → WB → PX)
2. Test custom dropdown (no PX call)
3. Test system dropdown (with PX call)
4. Test with/without reference_number
5. Performance testing (measure full chain latency)
6. Error scenario testing (PX down, WB timeout)
7. UAT with QA team

**Day 5 - Ticket Master Integration**:
1. Test Create Ticket Master workflow
   - Verify dropdown properties created correctly
   - Check `value` field structure
2. Test Update Ticket Master workflow
   - Verify dropdown config preserved/updated
3. Verify dropdowns render in tickets created via workflow

#### 9.2.2 Production Deployment

**Prerequisites**:
- All staging tests passed
- Performance benchmarks met
- Stakeholder approval received

**Deployment Window**: Low-traffic hours (e.g., 2 AM - 4 AM)

**Steps**:
1. **T-00:00**: Deploy backend to production
2. **T+00:05**: Verify backend health checks
3. **T+00:10**: Test API endpoint manually
4. **T+00:15**: Deploy frontend to production
5. **T+00:20**: Clear CDN cache
6. **T+00:25**: Smoke tests
7. **T+00:30**: Monitor logs and metrics
8. **T+01:00**: Deployment complete

### 9.3 Rollback Plan

**Triggers**:
- Critical bugs detected
- Performance degradation > 50%
- Error rate > 5%
- Stakeholder request

**Rollback Steps**:
1. Revert frontend deployment (5 minutes)
2. Revert backend deployment (5 minutes)
3. Verify system stable
4. Post-mortem analysis

**Impact**:
- No data loss (no schema changes)
- Dropdown properties become text inputs
- Users can continue working

### 9.4 Post-Deployment

**Monitoring** (First 24 Hours):
- Error rates
- Response times
- WB call success rates
- User feedback

**Success Metrics**:
- Zero critical bugs
- P95 response time < 500ms
- Error rate < 1%
- Positive user feedback

---

## 10. Security & Compliance

### 10.1 Authentication & Authorization

**Frontend → Plane**:
- Mechanism: Django session authentication
- Validation: Existing middleware
- Token: Session cookie (httpOnly, secure)

**Plane → WB**:
- Mechanism: Bearer token (if configured)
- Header: `Authorization: Bearer {WB_API_KEY}`
- Transmission: HTTPS only

### 10.2 Input Validation

**Workspace Slug**:
- Validated against user permissions
- SQL injection protection via ORM

**Issue Type ID**:
- UUID validation
- Ownership verification

**Identifier**:
- Whitelist validation
- Restricted to identifier_map keys

**Reference Number**:
- String sanitization
- No SQL execution

### 10.3 Data Privacy

**Dropdown Values**:
- Not stored in Plane database
- Fetched on-demand from WB
- No persistent caching

**User Data**:
- Only workspace and issue_type sent to WB
- No personal user information

### 10.4 Rate Limiting

**Considerations**:
- Multiple dropdowns on one page = multiple API calls
- Potential for abuse

**Recommendation**: Implement rate limiting (future enhancement)

### 10.5 PX Security Integration

**Server-to-Server Authentication**:
- WB stores PX credentials securely
- No PX credentials exposed to browser
- Separate credential per environment (staging, production)

**Request Validation**:
- PX validates request source (WB IP/credentials)
- Optional workspace_id validation
- Audit logging for all internal API calls

**Data Filtering**:
- PX returns only necessary fields
- Sensitive data (amounts, dates) can be omitted if not needed
- Configurable field visibility per endpoint

---

## 10A. Edge Cases & Fallback Behavior

### 10A.1 Missing Reference Number

**Scenario**: System-type dropdown requires reference_number but issue doesn't have one

**Behavior**:
1. Frontend sends request without reference_number (or empty string)
2. WB receives request, attempts PX call
3. PX returns error or WB detects missing context
4. WB returns empty array: `{ "data": { "records": [] } }`
5. Plane returns: `{ "options": [] }`
6. Frontend detects empty options
7. **Fallback**: Renders text input instead of dropdown

**User Experience**: User can manually enter value

### 10A.2 PX API Unavailable

**Scenario**: PX is down or unreachable

**Behavior**:
1. Frontend makes request
2. Plane proxies to WB
3. WB attempts to call PX
4. PX timeout or connection error
5. WB catches error, returns: `{ "data": { "records": [] }, "error": "External service unavailable" }`
6. Plane returns 200 OK with empty options
7. **Fallback**: Frontend renders text input

**Monitoring**: Log PX failures for alerting

### 10A.3 WB Timeout

**Scenario**: WB takes longer than 10 seconds

**Behavior**:
1. Frontend makes request
2. Plane proxies to WB with 10s timeout
3. Timeout occurs
4. Plane catches `requests.Timeout`
5. Plane returns 200 OK: `{ "options": [], "error": "Request timeout" }`
6. **Fallback**: Frontend renders text input

**Retry Logic**: No automatic retry (avoid cascading delays)

### 10A.4 Malformed Dropdown Configuration

**Scenario**: `value` field has invalid dropdown config

**Behavior**:
1. Frontend parses `value.dropdown_source_field`
2. Value is not string/array (e.g., number, object)
3. Frontend coerces to string or defaults to empty
4. **Fallback**: Renders text input

**Prevention**: Validate on backend during property creation

### 10A.5 Unknown Identifier

**Scenario**: Identifier not recognized by WB

**Behavior**:
1. Frontend sends request with identifier "unknownField"
2. Plane proxies to WB
3. WB doesn't recognize identifier
4. WB returns empty options or error
5. **Fallback**: Frontend renders text input

**Future Enhancement**: Add validation on Plane side with known identifiers list

### 10A.6 Network Failures

**Scenario**: Network issues between services

**Behavior**:
- **Plane → WB**: Return 200 with empty options, log error
- **WB → PX**: WB catches error, returns empty to Plane
- **Frontend → Plane**: Frontend shows error state, fallback to text

**Graceful Degradation**: Always allow manual text entry

### 10A.7 Concurrent Dropdown Requests

**Scenario**: Multiple dropdowns load simultaneously

**Behavior**:
1. Frontend makes parallel requests (one per dropdown)
2. Each request goes through full chain independently
3. No shared caching (v1)
4. All requests complete independently

**Future Enhancement**: 
- Batch requests
- Client-side caching
- Debouncing

### 10A.8 Stale Data

**Scenario**: Dropdown options change while user is viewing

**Behavior**:
- Options fetched at render time
- No real-time updates
- User sees options from when page loaded

**Future Enhancement**: Add refresh button or polling

---

## 10B. Cross-System Error Handling

### 10B.1 Error Flow Chain

```
Frontend → Plane → WB → PX
   ↓        ↓      ↓     ↓
Fallback  200 OK  200   Error
to Text   Empty   Empty  Details
Input     Options Array
```

### 10B.2 Error Response Standards

**Plane to Frontend**:
```json
{
  "options": [],
  "error": "Human-readable message"
}
```
Status: Always 200 OK (except 404 for workspace/auth failures)

**WB to Plane**:
```json
{
  "data": {
    "values": [],
    "records": []
  },
  "error": "Optional error message"
}
```

**PX to WB**:
```json
{
  "success": false,
  "error": "Error message",
  "code": "ERROR_CODE"
}
```

### 10B.3 Logging Strategy

**Plane Backend**:
- Log all WB requests with timing
- Log WB failures with full error
- Log timeout occurrences
- Include: workspace_id, issue_type_id, identifier, response_time

**WB (n8n)**:
- Log PX API calls and responses
- Log routing decisions (custom vs system)
- Log identifier lookups
- Include: request_id, timestamps, execution_time

**PX**:
- Log all internal API calls
- Include: caller (WB), workspace_id, query parameters
- Log query performance
- Security audit trail for data access

---

## 11. Performance & Monitoring

### 11.1 Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Response Time (P50)** | < 200ms | Application logs |
| **Response Time (P95)** | < 500ms | Application logs |
| **Response Time (P99)** | < 1000ms | Application logs |
| **WB Timeout** | 10s | Hardcoded |
| **Error Rate** | < 1% | Monitoring |
| **Success Rate** | > 99% | Monitoring |

### 11.2 Bottlenecks

**Identified Bottlenecks**:
1. WB response time (200-500ms)
2. PX database query time (100-300ms for system type)
3. Network latency (50-100ms)

**Mitigation**:
- 10s timeout prevents hanging requests
- Graceful fallback prevents UX blocking
- Parallel dropdown loading

### 11.3 Scalability Considerations

**Current Design** (No Caching):
- Every dropdown load = 1 WB call
- 1000 users × 5 dropdowns = 5000 WB calls

**Future Optimization** (Caching):
- Cache custom type responses (5 minutes)
- Cache system type responses (1 minute, keyed by reference_number)
- Reduces WB load by ~80%

**Load Estimates**:
- 1000 concurrent users
- 5 dropdowns per issue
- 200ms average response time
- Requires: 1000 × 5 / 200ms = 25 req/s to WB

### 11.4 Monitoring Metrics

**Application Metrics**:
- Request count per identifier
- Response time distribution
- Error rate by error type
- Cache hit rate (future)

**Infrastructure Metrics**:
- WB response time
- WB error rate
- Network latency
- Database connection pool

---

## 12. Risk Assessment

### 12.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **WB Unavailable** | Medium | Medium | Graceful fallback to text input |
| **WB Timeout** | Low | Low | 10s timeout, empty options response |
| **Performance Degradation** | Low | Medium | Monitoring, future caching |
| **Integration Bugs** | Medium | High | Comprehensive testing |
| **Data Format Changes** | Low | High | Version WB API responses |

### 12.2 Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Deployment Failure** | Low | High | Rollback plan, staging testing |
| **Configuration Error** | Medium | High | Environment variable validation |
| **WB Credentials Leaked** | Low | Critical | Secret management, rotation |
| **Increased Load** | Medium | Medium | Performance testing, scaling |

### 12.3 Business Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **User Confusion** | Low | Medium | Clear UI, help documentation |
| **Adoption Issues** | Low | Low | Training, documentation |
| **Data Inconsistency** | Low | Medium | Real-time fetching ensures freshness |

### 12.4 Mitigation Summary

**High Priority**:
- Comprehensive testing (unit, integration, UAT)
- Graceful error handling
- Rollback plan
- Monitoring and alerting

**Medium Priority**:
- Performance testing
- Documentation
- Training materials

**Low Priority**:
- Caching strategy (future)
- Advanced monitoring (future)

---

## 13. Appendix

### 13.1 Glossary

| Term | Definition |
|------|------------|
| **WB** | n8n workflow automation platform (WorkBench) |
| **PX** | External API system (ProjectX) - n8n calls PX APIs, not direct DB queries |
| **Custom Type** | Dropdown with global values |
| **System Type** | Dropdown with issue-specific values |
| **Identifier** | String key used by n8n to route requests |
| **Reference Number** | Issue context field (e.g., consignment number) |
| **Graceful Fallback** | Showing text input when dropdown fails |

### 13.2 Example Scenarios

#### Scenario 1: Create & Use Custom Dropdown

```
Step 1: Admin creates priority dropdown
POST /api/workspaces/acme/issue-type/123/custom-properties/
{
  "name": "Priority",
  "data_type": "dropdown",
  "value": {
    "dropdown_source_type": "custom",
    "dropdown_source_field": "priorityLevels"
  }
}

Step 2: User opens issue
- Frontend loads custom properties
- Sees "Priority" field with type "dropdown"

Step 3: User clicks Priority field
- Frontend calls GET /issue/dropdown-options/priorityLevels/
  with query params: ?issue_type_id=uuid&issue_type_custom_property_id=uuid&custom_property_id=uuid
- Plane proxies to WB
- WB identifies as custom type and returns ["High", "Medium", "Low", "Critical"]
- Dropdown displays with 4 options

Step 4: User selects "High"
- Value saved to issue's custom properties
```

#### Scenario 2: Create & Use System Dropdown

```
Step 1: Admin creates invoice dropdown
POST /api/workspaces/acme/issue-type/123/custom-properties/
{
  "name": "Invoice Number",
  "data_type": "dropdown",
  "value": {
    "dropdown_source_type": "system",
    "dropdown_source_field": "consignmentInvoiceNumber"
  }
}

Step 2: User opens issue (reference_number: "CN12345")
- Frontend loads custom properties
- Sees "Invoice Number" field with type "dropdown"

Step 3: User clicks Invoice Number field
- Frontend calls GET /issue/dropdown-options/consignmentInvoiceNumber/
  with query params: ?issue_type_id=uuid&issue_type_custom_property_id=uuid&custom_property_id=uuid&reference_number=CN12345
- Plane proxies to WB with all parameters
- WB identifies as system type
- WB calls PX API for invoices related to CN12345
- WB returns invoice numbers
- Dropdown displays issue-specific invoices

Step 4: User selects invoice
- Value saved to issue's custom properties
```

### 13.3 Configuration Examples

#### Production Configuration

```bash
# .env
WB_BASE_URL=https://n8n.production.example.com
WB_API_KEY=prod_key_abc123xyz
DEBUG=False
ALLOWED_HOSTS=plane.example.com
```

#### Staging Configuration

```bash
# .env
WB_BASE_URL=https://n8n.staging.example.com
WB_API_KEY=staging_key_def456uvw
DEBUG=True
ALLOWED_HOSTS=plane-staging.example.com
```

