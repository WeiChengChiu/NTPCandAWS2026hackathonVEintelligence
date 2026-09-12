"""Verify the AWS default profile works (boto3 only, no AWS CLI needed).

Usage:
    python scripts/verify_aws.py
"""

import sys
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


def main() -> int:
    session = boto3.Session()  # resolves [default] from ~/.aws/{credentials,config}
    creds = session.get_credentials()
    if creds is None:
        print("No credentials resolved. Check ~/.aws/credentials [default].")
        return 1

    frozen = creds.get_frozen_credentials()
    print(f"Resolved via   : {creds.method}")
    print(f"Region         : {session.region_name}")
    print(f"Access Key ID  : {frozen.access_key}")
    print(f"Session token  : {'present' if frozen.token else 'absent'}")

    try:
        identity = session.client("sts").get_caller_identity()
    except NoCredentialsError:
        print("boto3 could not find usable credentials.")
        return 1
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "Unknown")
        print(f"STS call failed [{code}]: {exc.response.get('Error', {}).get('Message', exc)}")
        if code in {"ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId"}:
            print("The temporary credentials look expired. Grab a fresh set from Workshop Studio.")
        return 1

    print("-" * 46)
    print(f"Account ID     : {identity['Account']}")
    print(f"ARN            : {identity['Arn']}")
    print(f"UserId         : {identity['UserId']}")
    print(f"Checked at     : {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
