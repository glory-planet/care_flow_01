"""Amazon Cognito 인증 클라이언트.

Cognito User Pool을 통한 로그인/토큰 검증을 담당한다.
"""

import boto3

REGION = "us-east-1"
USER_POOL_ID = "us-east-1_5NS1dVpbR"
CLIENT_ID = "4g473rdqnkcvbects7adlh2u4g"

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = boto3.client("cognito-idp", region_name=REGION)
    return _client


def authenticate(username, password):
    """Cognito로 사용자를 인증한다.

    성공 시: {"authenticated": True, "tokens": {...}, "username": str, "groups": [...]}
    실패 시: {"authenticated": False, "error": str}
    """
    client = _get_client()
    try:
        response = client.initiate_auth(
            ClientId=CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password,
            },
        )
    except client.exceptions.NotAuthorizedException:
        return {"authenticated": False, "error": "invalid credentials"}
    except client.exceptions.UserNotFoundException:
        return {"authenticated": False, "error": "user not found"}
    except Exception as e:
        return {"authenticated": False, "error": str(e)}

    tokens = response.get("AuthenticationResult", {})

    # 사용자 그룹 조회 (역할 확인)
    groups = get_user_groups(username)

    # 사용자 속성 조회
    user_attrs = get_user_attributes(username)

    return {
        "authenticated": True,
        "tokens": {
            "access_token": tokens.get("AccessToken"),
            "id_token": tokens.get("IdToken"),
            "refresh_token": tokens.get("RefreshToken"),
        },
        "username": username,
        "groups": groups,
        "attributes": user_attrs,
    }


def get_user_groups(username):
    """사용자가 속한 그룹 목록을 반환한다."""
    client = _get_client()
    try:
        response = client.admin_list_groups_for_user(
            Username=username,
            UserPoolId=USER_POOL_ID,
        )
        return [g["GroupName"] for g in response.get("Groups", [])]
    except Exception:
        return []


def get_user_attributes(username):
    """사용자의 Cognito 속성을 dict로 반환한다."""
    client = _get_client()
    try:
        response = client.admin_get_user(
            UserPoolId=USER_POOL_ID,
            Username=username,
        )
        attrs = {}
        for attr in response.get("UserAttributes", []):
            attrs[attr["Name"]] = attr["Value"]
        return attrs
    except Exception:
        return {}


def verify_token(access_token):
    """Access Token의 유효성을 검증한다.

    성공 시: {"valid": True, "username": str}
    실패 시: {"valid": False}
    """
    client = _get_client()
    try:
        response = client.get_user(AccessToken=access_token)
        username = response.get("Username")
        return {"valid": True, "username": username}
    except Exception:
        return {"valid": False}
