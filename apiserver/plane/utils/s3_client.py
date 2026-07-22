# Python imports
import os

# Third party imports
import boto3
from botocore.client import Config


def _resolve_credentials(presign=False):
    """Resolve the static AWS credentials to use for an S3 client.

    - When ``presign`` is True the dedicated long-lived keys
      (``AWS_S3_ACCESS_KEY`` / ``AWS_S3_SECRET_KEY``) are preferred. These
      exist so that presigned GET URLs can outlive the short-lived session
      tokens issued by IRSA (IAM Roles for Service Accounts). If they are not
      configured we fall back to the standard keys (e.g. MinIO / self-host).
    - Otherwise the standard keys (``AWS_ACCESS_KEY_ID`` /
      ``AWS_SECRET_ACCESS_KEY``) are used.

    When no keys can be resolved ``(None, None)`` is returned so that boto3
    falls back to its default credential provider chain — i.e. the IRSA
    web-identity token or instance role.
    """
    if presign:
        access_key = os.environ.get("AWS_S3_ACCESS_KEY") or os.environ.get(
            "AWS_ACCESS_KEY_ID"
        )
        secret_key = os.environ.get("AWS_S3_SECRET_KEY") or os.environ.get(
            "AWS_SECRET_ACCESS_KEY"
        )
        return access_key, secret_key

    return (
        os.environ.get("AWS_ACCESS_KEY_ID"),
        os.environ.get("AWS_SECRET_ACCESS_KEY"),
    )


def get_s3_client(
    endpoint_url=None,
    region_name=None,
    presign=False,
    signature_version="s3v4",
):
    """Build a boto3 S3 client.

    Static credentials are only passed to boto3 when both an access key and a
    secret key can be resolved. When they are absent boto3 resolves
    credentials through its default provider chain, which for a pod running
    with IRSA means the injected web-identity token.

    Set ``presign=True`` for clients used to sign presigned GET URLs so the
    dedicated ``AWS_S3_ACCESS_KEY`` / ``AWS_S3_SECRET_KEY`` credentials are
    used instead of the (potentially short-lived) IRSA session.
    """
    access_key, secret_key = _resolve_credentials(presign=presign)

    kwargs = {"config": Config(signature_version=signature_version)}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if region_name:
        kwargs["region_name"] = region_name
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key

    return boto3.client("s3", **kwargs)
