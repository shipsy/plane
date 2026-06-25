# Django imports
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.api.serializers import (
    IssueTypeSerializer,
    IssueTypeCustomPropertySerializer,
    UserLiteSerializer,
)
from plane.app.permissions import ProjectMemberPermission
from plane.db.models import (
    IssueType,
    Profile,
    Project,
    ProjectMember,
    User,
    Workspace,
    WorkspaceMember,
)

from .base import BaseAPIView
from .member import ProjectMemberAPIEndpoint


class TicketMasterAPIEndpoint(BaseAPIView):
    """
    Consolidated endpoint that creates an issue type, its custom properties,
    and resolves / creates assignees in a single atomic transaction.

    Replaces three separate calls from the n8n flow:
      1) POST /workspaces/<slug>/issue-type/
      2) POST /workspaces/<slug>/issue-type/<id>/custom-properties/  (N times)
      3) GET + POST /workspaces/<slug>/projects/<id>/members/        (1 + M times)
    """

    permission_classes = [ProjectMemberPermission]

    def post(self, request, slug, project_id):
        issue_type_data = request.data.get("issue_type") or {}
        custom_properties_data = request.data.get("custom_properties") or []
        assignees_data = request.data.get("assignees") or []

        # ---- pre-flight validation (outside the transaction) ----
        workspace = Workspace.objects.filter(slug=slug).first()
        project = Project.objects.filter(pk=project_id).first()
        if not workspace or not project:
            return Response(
                {"error": "Provided workspace or project does not exist"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        issue_type_name = issue_type_data.get("name")
        if not issue_type_name:
            return Response(
                {"error": "Invalid issue_type", "details": {"name": "This field is required"}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_issue_type = IssueType.objects.filter(
            name=issue_type_name, workspace=workspace
        ).first()
        if existing_issue_type:
            return Response(
                {
                    "error": "Issue Type with same name already exists",
                    "id": str(existing_issue_type.id),
                },
                status=status.HTTP_409_CONFLICT,
            )

        # ---- one atomic block wrapping all three writes ----
        try:
            with transaction.atomic():
                issue_type = self._create_issue_type(
                    request, workspace, issue_type_data
                )
                created_properties = self._create_custom_properties(
                    issue_type, custom_properties_data
                )
                resolved_assignees = self._resolve_assignees(
                    workspace, project, assignees_data
                )
        except _TicketMasterError as exc:
            return Response(exc.body, status=exc.status_code)
        except IntegrityError as exc:
            return Response(
                {"error": "Database integrity error", "details": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "issue_type": IssueTypeSerializer(issue_type).data,
                "custom_properties": created_properties,
                "assignees": resolved_assignees,
            },
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # Step 1 — issue type
    # ------------------------------------------------------------------
    def _create_issue_type(self, request, workspace, data):
        serializer = IssueTypeSerializer(
            data=data, context={"workspace_id": workspace.id}
        )
        if not serializer.is_valid():
            raise _TicketMasterError(
                status.HTTP_400_BAD_REQUEST,
                {"error": "Invalid issue_type", "details": serializer.errors},
            )
        serializer.save()
        issue_type = IssueType.objects.get(pk=serializer.data["id"])
        issue_type.created_at = data.get("created_at", timezone.now())
        issue_type.created_by_id = data.get("created_by", request.user.id)
        issue_type.save(update_fields=["created_at", "created_by"])
        return issue_type

    # ------------------------------------------------------------------
    # Step 2 — custom properties (bulk loop, single serializer per row)
    # ------------------------------------------------------------------
    def _create_custom_properties(self, issue_type, properties):
        created = []
        errors = []
        for index, cp_data in enumerate(properties):
            serializer = IssueTypeCustomPropertySerializer(
                data=cp_data, context={"issue_type_id": issue_type.id}
            )
            if not serializer.is_valid():
                errors.append({"index": index, "errors": serializer.errors})
                continue
            try:
                # Savepoint per row: a caught IntegrityError rolls back only
                # this INSERT and leaves the outer atomic() block usable.
                # Without this, Postgres aborts the whole transaction on the
                # first integrity error and every subsequent query raises
                # TransactionManagementError, which would escape to a 500.
                with transaction.atomic():
                    serializer.save()
            except IntegrityError as exc:
                if "already exists" in str(exc) or "unique" in str(exc).lower():
                    errors.append(
                        {"index": index, "name": "The Property Name is already taken"}
                    )
                    continue
                raise
            created.append(serializer.data)

        if errors:
            # Any failure here is treated as "invalid custom_properties" and the
            # whole transaction rolls back. A pure-name-conflict batch is mapped
            # to 410 to match the standalone endpoint's behavior.
            if all("name" in err and "errors" not in err for err in errors):
                raise _TicketMasterError(
                    status.HTTP_410_GONE,
                    {"error": "Invalid custom_properties", "details": errors},
                )
            raise _TicketMasterError(
                status.HTTP_400_BAD_REQUEST,
                {"error": "Invalid custom_properties", "details": errors},
            )
        return created

    # ------------------------------------------------------------------
    # Step 3 — assignees (reuses ProjectMemberAPIEndpoint helpers)
    # ------------------------------------------------------------------
    def _resolve_assignees(self, workspace, project, assignees):
        if not assignees:
            return []

        # Pre-validate every email up front so we never start a write loop
        # we already know is going to be rolled back. Cheaper than letting
        # the writes happen and relying on the outer atomic() to undo them.
        validation_errors = []
        normalized = []
        for index, assignee in enumerate(assignees):
            raw_email = assignee.get("email")
            if not raw_email:
                validation_errors.append(
                    {"index": index, "email": "This field is required"}
                )
                normalized.append(None)
                continue
            email = raw_email.lower()
            try:
                validate_email(email)
            except DjangoValidationError:
                validation_errors.append(
                    {"index": index, "email": "Invalid email provided"}
                )
                normalized.append(None)
                continue
            normalized.append(email)

        if validation_errors:
            raise _TicketMasterError(
                status.HTTP_400_BAD_REQUEST,
                {"error": "Invalid assignees", "details": validation_errors},
            )

        resolved = []

        for index, assignee in enumerate(assignees):
            email = normalized[index]

            # Savepoint per assignee so a per-row failure rolls back only this
            # assignee's writes (user / profile / memberships) without
            # poisoning the outer atomic() block.
            with transaction.atomic():
                user = User.objects.filter(email=email).first()

                if not user:
                    user = ProjectMemberAPIEndpoint.create_user(
                        {
                            "email": email,
                            "display_name": assignee.get("display_name"),
                            "first_name": assignee.get("first_name", ""),
                            "last_name": assignee.get("last_name", ""),
                            "role": assignee.get("role", 15),
                            "hub_codes": assignee.get("hub_codes") or [],
                            "username": assignee.get("username"),
                        }
                    )
                    profile, _ = Profile.objects.get_or_create(user=user)
                    profile.last_workspace_id = workspace.id
                    profile.onboarding_step.update(
                        {"profile_complete": True, "workspace_join": True}
                    )
                    profile.is_tour_completed = True
                    profile.is_onboarded = True
                    profile.company_name = workspace.name
                    profile.save()
                elif assignee.get("hub_codes") is not None:
                    user.hub_codes = assignee.get("hub_codes")
                    user.save(update_fields=["hub_codes"])

                if not WorkspaceMember.objects.filter(
                    workspace=workspace, member=user
                ).exists():
                    ProjectMemberAPIEndpoint.create_workspace_member(
                        workspace.id, user, role=assignee.get("role", 15)
                    )

                if not ProjectMember.objects.filter(
                    project=project, member=user
                ).exists():
                    ProjectMemberAPIEndpoint.create_project_member(
                        project.id, user, role=assignee.get("role", 15)
                    )
                # "Already a project member" is a silent no-op here — not a
                # 400 — because for the n8n flow this is the normal case.

            resolved.append(UserLiteSerializer(user).data)

        return resolved


class _TicketMasterError(Exception):
    """Internal control-flow exception that triggers transaction rollback
    and carries the response body / status code back to the view."""

    def __init__(self, status_code, body):
        super().__init__(body.get("error", "TicketMaster error"))
        self.status_code = status_code
        self.body = body
