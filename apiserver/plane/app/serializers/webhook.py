# Third party imports
from rest_framework import serializers

# Module imports
from .base import DynamicBaseSerializer
from plane.db.models import Webhook, WebhookLog
from plane.db.models.webhook import validate_domain, validate_schema
from plane.utils.url_validator import BlockedURLError, validate_outbound_url


class WebhookSerializer(DynamicBaseSerializer):
    url = serializers.URLField(validators=[validate_schema, validate_domain])

    def validate_url(self, url):
        # Block Plane's own domains as well as any internal destination
        disallowed_domains = ["plane.so"]
        request = self.context.get("request")
        if request:
            # Remove port if present
            disallowed_domains.append(request.get_host().split(":")[0])

        try:
            validate_outbound_url(url, blocked_domains=disallowed_domains)
        except BlockedURLError as e:
            raise serializers.ValidationError(str(e))
        return url

    class Meta:
        model = Webhook
        fields = "__all__"
        read_only_fields = [
            "workspace",
            "secret_key",
        ]


class WebhookLogSerializer(DynamicBaseSerializer):
    class Meta:
        model = WebhookLog
        fields = "__all__"
        read_only_fields = ["workspace", "webhook"]
