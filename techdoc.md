# Technical Specification: Dropdown Custom Properties

## 1. Executive Summary

### 1.1 Purpose

This document specifies the technical implementation for adding dropdown support to Issue Type Custom Properties in Plane. The feature enables dynamic dropdown fields with values fetched from WB (n8n workflow) at runtime.

### 1.2 Scope

**In Scope**:
- Dropdown data type for custom properties
- Two dropdown variants: Custom and System
- Real-time value fetching from WB
- Frontend dropdown rendering
- Error handling and fallback mechanisms

**Out of Scope**:
- Multi-select dropdowns
- Client-side value caching
- Offline dropdown support
- Database schema changes

### 1.3 Key Benefits

| Benefit | Description |
|---------|-------------|
| **Dynamic Data** | Values fetched in real-time from external systems |
| **Zero Schema Changes** | Uses existing database fields |
| **Flexible** | Supports both global and context-specific dropdowns |
| **Resilient** | Graceful fallback to text input on failures |
| **Scalable** | Easy to add new dropdown types |

### 1.4 Success Criteria

- [ ] Users can create dropdown custom properties
- [ ] Dropdowns fetch values from WB at render time
- [ ] System type dropdowns use issue context (reference_number)
- [ ] Graceful fallback when WB unavailable
- [ ] Response time < 500ms for 95% of requests
- [ ] Zero database migrations required

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
│  ┌──────────────┐       ┌──────────────┐                   │
│  │   Frontend   │◄─────►│   Backend    │                   │
│  │  (React)     │       │  (Django)    │                   │
│  └──────────────┘       └───────┬──────┘                   │
│                                  │                           │
└──────────────────────────────────┼───────────────────────────┘
                                   │
                                   │ HTTPS
                                   ↓
                         ┌──────────────────┐
                         │   WB (n8n)       │
                         │   Workflows      │
                         └────────┬─────────┘
                                  │
                                  │ Query
                                  ↓
                         ┌──────────────────┐
                         │   PX Database    │
                         └──────────────────┘
```

### 3.2 Component Architecture

**Frontend Components**:
- `CustomProperties.tsx` - Dropdown rendering
- State management for dropdown options
- Loading states and error handling

**Backend Components**:
- `DropdownOptionsAPIEndpoint` - Proxy endpoint
- Request validation and formatting
- WB integration logic

**External Systems**:
- WB (n8n) - Workflow automation
- PX - External database

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
-- Existing table: isssue_type_custom_properties
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
  "ticket_type_id": "uuid",
  "data_type": "dropdown",
  "identifier": "priorityLevels",
  "workspace_id": "uuid"
}
```

**WB Response**:
```json
{
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
  "ticket_type_id": "uuid",
  "data_type": "dropdown",
  "identifier": "consignmentInvoiceNumber",
  "reference_number": "CN12345",
  "workspace_id": "uuid"
}
```

**WB Response**:
```json
{
  "data": {
    "data": [
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

## 5. Implementation Specifications

### 5.1 Backend Implementation

#### 5.1.1 New API Endpoint

**File**: `apiserver/plane/api/views/issue_type.py`

**Class**: `DropdownOptionsAPIEndpoint`

**Method**: `POST`

**Purpose**: Proxy dropdown value requests to WB

**Key Logic**:
1. Validate workspace and issue_type access
2. Extract identifier from URL path
3. Get reference_number from request body (optional)
4. Map identifier to WB endpoint
5. Build WB request with ticket_type_id and data_type
6. Call WB with 10s timeout
7. Parse WB response
8. Return formatted options

**Error Handling**:
- Workspace not found → 404
- Issue type not found → 404
- Unknown identifier → 400
- WB timeout → 200 with empty options
- WB error → 200 with empty options
- Network error → 200 with empty options

#### 5.1.2 URL Routing

**File**: `apiserver/plane/api/urls/issue_type.py`

**New Route**:
```python
path(
    "workspaces/<str:slug>/issue-type/<uuid:issue_type>/dropdown-options/<str:identifier>/",
    DropdownOptionsAPIEndpoint.as_view(),
    name="dropdown-options",
)
```

**URL Pattern**: `/api/workspaces/{slug}/issue-type/{issue_type_id}/dropdown-options/{identifier}/`

#### 5.1.3 Identifier Mapping

**Purpose**: Map identifiers to WB endpoints

**Structure**:
```python
identifier_map = {
    'priorityLevels': {
        'endpoint': '/webhook/fetch-dropdown-values',
        'requires_reference': False
    },
    'consignmentInvoiceNumber': {
        'endpoint': '/webhook/consignment-invoice-fetch',
        'requires_reference': True
    }
}
```

**Adding New Identifiers**:
1. Add entry to identifier_map
2. Create corresponding WB workflow
3. Update documentation
4. Add tests

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
5. Build API request (include reference_number for system)
6. Set loading state
7. Call `/dropdown-options/{identifier}/`
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

**Required Workflows**:

1. **Fetch Dropdown Values** (Custom Type)
   - Endpoint: `/webhook/fetch-dropdown-values`
   - Input: `{ticket_type_id, data_type, identifier, workspace_id}`
   - Output: `{data: {values: [...]}}`

2. **Consignment Invoice Fetch** (System Type)
   - Endpoint: `/webhook/consignment-invoice-fetch`
   - Input: `{ticket_type_id, data_type, identifier, reference_number, workspace_id}`
   - Output: `{data: {data: [{invoice_number: "..."}]}}`

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

**Endpoint**: `POST /api/workspaces/{slug}/issue-type/{issue_type_id}/dropdown-options/{identifier}/`

**Authentication**: Session-based (existing)

**Path Parameters**:
- `slug` (string): Workspace slug
- `issue_type_id` (uuid): Issue type ID
- `identifier` (string): Dropdown identifier

**Request Headers**:
```
Content-Type: application/json
Cookie: sessionid=...
```

**Request Body (Custom Type)**:
```json
{}
```

**Request Body (System Type)**:
```json
{
  "reference_number": "CN12345"
}
```

**Success Response**: `200 OK`
```json
{
  "options": ["High", "Medium", "Low", "Critical"]
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

**Endpoint**: `POST {WB_BASE_URL}/webhook/{endpoint}`

**Headers**:
```
Content-Type: application/json
User-Agent: Plane-API
Authorization: Bearer {WB_API_KEY}  (if configured)
```

**Body (Standard)**:
```json
{
  "ticket_type_id": "550e8400-e29b-41d4-a716-446655440000",
  "data_type": "dropdown",
  "identifier": "priorityLevels",
  "workspace_id": "650e8400-e29b-41d4-a716-446655440000"
}
```

**Body (With Context)**:
```json
{
  "ticket_type_id": "550e8400-e29b-41d4-a716-446655440000",
  "data_type": "dropdown",
  "identifier": "consignmentInvoiceNumber",
  "reference_number": "CN12345",
  "workspace_id": "650e8400-e29b-41d4-a716-446655440000"
}
```

#### 6.3.2 Response from WB

**Custom Type Response**:
```json
{
  "data": {
    "values": ["High", "Medium", "Low", "Critical"]
  }
}
```

**System Type Response**:
```json
{
  "data": {
    "data": [
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
Frontend: POST /dropdown-options/priorityLevels/
    Body: {}
    ↓
Plane Backend
    ↓
    Validates access
    ↓
    Maps identifier to WB endpoint
    ↓
    POST {WB_BASE_URL}/webhook/fetch-dropdown-values
    {
      "ticket_type_id": "uuid",
      "data_type": "dropdown",
      "identifier": "priorityLevels"
    }
    ↓
WB (n8n)
    ↓
    Looks up configuration
    ↓
    Returns: {"data": {"values": ["High", "Medium", "Low"]}}
    ↓
Plane Backend
    ↓
    Extracts values
    ↓
    Returns: {"options": ["High", "Medium", "Low"]}
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
Frontend: POST /dropdown-options/consignmentInvoiceNumber/
    Body: {"reference_number": "CN12345"}
    ↓
Plane Backend
    ↓
    Validates access
    ↓
    Maps identifier to WB endpoint
    ↓
    POST {WB_BASE_URL}/webhook/consignment-invoice-fetch
    {
      "ticket_type_id": "uuid",
      "data_type": "dropdown",
      "identifier": "consignmentInvoiceNumber",
      "reference_number": "CN12345"
    }
    ↓
WB (n8n)
    ↓
    Queries PX Database with CN12345
    ↓
    Returns: {
      "data": {
        "data": [
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
    Returns: {"options": ["INV-001", "INV-002"]}
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
Frontend: POST /dropdown-options/identifier/
    ↓
Plane Backend
    ↓
    POST to WB
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
   - Mock WB response with data
   - Call endpoint with system identifier and reference_number
   - Assert WB called with context
   - Assert options extracted correctly

3. **test_missing_reference_number**
   - Call system endpoint without reference_number
   - Assert returns empty options with error

4. **test_wb_timeout**
   - Mock requests.Timeout exception
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


## 9. Deployment Plan

### 9.1 Pre-Deployment Checklist

**Infrastructure**:
- [ ] `WB_BASE_URL` configured in all environments
- [ ] `WB_API_KEY` configured (if required)
- [ ] WB workflows deployed and tested
- [ ] Network connectivity verified

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

### 9.2 Deployment Steps

#### 9.2.1 Staging Deployment

**Day 1 - Backend**:
1. Deploy backend changes to staging
2. Restart Django application servers
3. Verify `/dropdown-options/` endpoint accessible
4. Test with curl/Postman
5. Verify WB integration working

**Day 2 - Frontend**:
1. Deploy frontend changes to staging
2. Clear CDN cache
3. Verify component renders correctly
4. Test dropdown loading
5. Test error scenarios

**Day 3 - Integration Testing**:
1. Full end-to-end testing
2. Test both dropdown types
3. Test with/without reference_number
4. Performance testing
5. UAT with QA team


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
| **PX** | External database system (ProjectX) |
| **Custom Type** | Dropdown with global values |
| **System Type** | Dropdown with issue-specific values |
| **Identifier** | String key mapping to WB endpoint |
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
- Frontend calls /dropdown-options/priorityLevels/
- Plane calls WB
- WB returns ["High", "Medium", "Low", "Critical"]
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
- Frontend calls /dropdown-options/consignmentInvoiceNumber/
  with body: {"reference_number": "CN12345"}
- Plane calls WB with CN12345
- WB queries PX for invoices related to CN12345
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


