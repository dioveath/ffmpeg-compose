import os
import logging
from minio import Minio

logger = logging.getLogger(__name__)

minio_client = Minio(
    os.environ.get('MINIO_ENDPOINT', 'localhost:9000'),
    access_key=os.environ.get('MINIO_ACCESS_KEY', 'minioadmin'),
    secret_key=os.environ.get('MINIO_SECRET_KEY', 'minioadmin'),
    secure=os.environ.get('MINIO_SECURE', 'False').lower() == 'true'
)

# Ensure bucket exists
bucket_name = os.environ.get('MINIO_BUCKET_NAME', 'video-storage')
try:
    if not minio_client.bucket_exists(bucket_name):
        minio_client.make_bucket(bucket_name)
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                }
            ]
        }
        policy_str = json.dumps(policy)
        minio_client.set_bucket_policy(bucket_name, policy_str)
        logger.info(f"Bucket '{bucket_name}' created and policy set.")
except Exception as e:
    logger.error(f"Failed to create or set policy for bucket '{bucket_name}': {str(e)}")

minio_public_endpoint = os.environ.get('MINIO_PUBLIC_ENDPOINT', 'http://localhost:9000')