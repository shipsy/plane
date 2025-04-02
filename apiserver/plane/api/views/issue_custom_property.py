from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import F

from plane.db.models import IssueCustomProperty, IssueTypeCustomProperty, Project
from plane.api.permissions import ProjectEntityPermission

class IssueCustomPropertyViewSet(viewsets.ModelViewSet):
    permission_classes = [ProjectEntityPermission]
    model = IssueCustomProperty
    
    def get_queryset(self):
        return IssueCustomProperty.objects.filter(
            workspace__slug=self.kwargs.get("slug"),
            project_id=self.kwargs.get("project_id"),
            deleted=False
        )
    
    @action(detail=False, methods=["get"])
    def issue_type_properties(self, request, slug, project_id):
        """
        Returns all custom properties for issue types in the project
        """
        issue_type_id = request.query_params.get("issue_type_id", None)
        
        try:
            project = Project.objects.get(id=project_id, workspace__slug=slug, deleted=False)
        except Project.DoesNotExist:
            return Response({"error": "Project not found"}, status=404)
            
        queryset = IssueTypeCustomProperty.objects.filter(
            issue_type__workspace__slug=slug,
            project_id=project_id,
            deleted=False
        )
        
        if issue_type_id:
            queryset = queryset.filter(issue_type_id=issue_type_id)
            
        custom_properties = queryset.annotate(
            property_key=F("key")
        ).values("id", "property_key", "name")
        
        return Response(custom_properties)
