# Python imports
import os

# Third party imports
from botocore.exceptions import ClientError
from urllib.parse import quote

# Module imports
from plane.utils.exception_logger import log_exception
from plane.utils.s3_client import get_s3_client
from storages.backends.s3boto3 import S3Boto3Storage


class S3Storage(S3Boto3Storage):

    file_overwrite = False
    location = ''
    def url(self, name, parameters=None, expire=None, http_method=None):
        return name

    """S3 storage class to generate presigned URLs for S3 objects"""
    def get_available_name(self, name, max_length=None):
        # TODO: something with max_length?
        if self.file_overwrite:
            return name
        return super().get_available_name(name, max_length=max_length)

    def __init__(self, request=None):
        # Use the AWS_S3_BUCKET_NAME environment variable for the bucket name
        self.aws_storage_bucket_name = os.environ.get("AWS_S3_BUCKET_NAME")
        # Use the AWS_REGION environment variable for the region
        self.aws_region = os.environ.get("AWS_REGION")
        # Use the AWS_S3_ENDPOINT_URL environment variable for the endpoint URL
        self.aws_s3_endpoint_url = os.environ.get(
            "AWS_S3_ENDPOINT_URL"
        ) or os.environ.get("MINIO_ENDPOINT_URL")

        if os.environ.get("USE_MINIO") == "1":
            endpoint_url = (
                f"https://{request.get_host()}"
                if request
                else self.aws_s3_endpoint_url
            )
        else:
            endpoint_url = self.aws_s3_endpoint_url

        # General-purpose S3 client. Resolves credentials via the default
        # provider chain (IRSA) when static keys are absent.
        self.s3_client = get_s3_client(
            endpoint_url=endpoint_url,
            region_name=self.aws_region,
        )
        # Dedicated client for signing presigned GET URLs with the long-lived
        # AWS_S3_ACCESS_KEY / AWS_S3_SECRET_KEY credentials.
        self.presigned_s3_client = get_s3_client(
            endpoint_url=endpoint_url,
            region_name=self.aws_region,
            presign=True,
        )

    def generate_presigned_post(
        self, object_name, file_type, file_size, expiration=3600
    ):
        """Generate a presigned URL to upload an S3 object"""
        fields = {
            "Content-Type": file_type,
        }

        conditions = [
            {"bucket": self.aws_storage_bucket_name},
            ["content-length-range", 1, file_size],
            {"Content-Type": file_type},
        ]

        # Add condition for the object name (key)
        if object_name.startswith("${filename}"):
            conditions.append(
                ["starts-with", "$key", object_name[: -len("${filename}")]]
            )
        else:
            fields["key"] = object_name
            conditions.append({"key": object_name})

        # Generate the presigned POST URL
        try:
            
            # Generate a presigned URL for the S3 object
            response = self.s3_client.generate_presigned_post(
                Bucket=self.aws_storage_bucket_name,
                Key=object_name,
                Fields=fields,
                Conditions=conditions,
                ExpiresIn=expiration,
            )
            
        # Handle errors
        except ClientError as e:
            print(f"Error generating presigned POST URL: {e}")
            return None

        return response

    def _get_content_disposition(self, disposition, filename=None):
        """Helper method to generate Content-Disposition header value"""
        if filename:
            # Encode the filename to handle special characters
            encoded_filename = quote(filename)
            return f"{disposition}; filename*=UTF-8''{encoded_filename}"
        return disposition

    def generate_presigned_url(
        self,
        object_name,
        expiration=3600,
        http_method="GET",
        disposition="inline",
        filename=None,
    ):
        content_disposition = self._get_content_disposition(
            disposition, filename
        )
        """Generate a presigned URL to share an S3 object"""
        try:
            response = self.presigned_s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.aws_storage_bucket_name,
                    "Key": str(object_name),
                    "ResponseContentDisposition": content_disposition,
                },
                ExpiresIn=expiration,
                HttpMethod=http_method,
            )
        except ClientError as e:
            log_exception(e)
            return None

        # The response contains the presigned URL
        return response

    def get_object_metadata(self, object_name):
        """Get the metadata for an S3 object"""
        try:
            response = self.s3_client.head_object(
                Bucket=self.aws_storage_bucket_name, Key=object_name
            )
        except ClientError as e:
            log_exception(e)
            return None

        return {
            "ContentType": response.get("ContentType"),
            "ContentLength": response.get("ContentLength"),
            "LastModified": (
                response.get("LastModified").isoformat()
                if response.get("LastModified")
                else None
            ),
            "ETag": response.get("ETag"),
            "Metadata": response.get("Metadata", {}),
        }
