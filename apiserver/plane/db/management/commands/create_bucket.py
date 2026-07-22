# Python imports
import os
from botocore.exceptions import ClientError

# Django imports
from django.core.management import BaseCommand

# Module imports
from plane.utils.s3_client import get_s3_client


class Command(BaseCommand):
    help = "Create the default bucket for the instance"

    def handle(self, *args, **options):
        # Create a session using the credentials from Django settings
        try:
            s3_client = get_s3_client(
                endpoint_url=os.environ.get("AWS_S3_ENDPOINT_URL"),
                region_name=os.environ.get("AWS_REGION"),
            )
            # Get the bucket name from the environment
            bucket_name = os.environ.get("AWS_S3_BUCKET_NAME")
            self.stdout.write(self.style.NOTICE("Checking bucket..."))
            # Check if the bucket exists
            s3_client.head_bucket(Bucket=bucket_name)
            # If the bucket exists, print a success message
            self.stdout.write(
                self.style.SUCCESS(f"Bucket '{bucket_name}' exists.")
            )
            return
        except ClientError as e:
            error_code = int(e.response["Error"]["Code"])
            bucket_name = os.environ.get("AWS_S3_BUCKET_NAME")
            if error_code == 404:
                # Bucket does not exist, create it
                self.stdout.write(
                    self.style.WARNING(
                        f"Bucket '{bucket_name}' does not exist. Creating bucket..."
                    )
                )
                try:
                    s3_client.create_bucket(Bucket=bucket_name)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Bucket '{bucket_name}' created successfully."
                        )
                    )

                # Handle the exception if the bucket creation fails
                except ClientError as create_error:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to create bucket: {create_error}"
                        )
                    )

            # Handle the exception if access to the bucket is forbidden
            elif error_code == 403:
                # Access to the bucket is forbidden
                self.stdout.write(
                    self.style.ERROR(
                        f"Access to the bucket '{bucket_name}' is forbidden. Check permissions."
                    )
                )
            else:
                # Another ClientError occurred
                self.stdout.write(
                    self.style.ERROR(f"Failed to check bucket: {e}")
                )
        except Exception as ex:
            # Handle any other exception
            self.stdout.write(self.style.ERROR(f"An error occurred: {ex}"))
