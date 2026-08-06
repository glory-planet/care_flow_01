"""AWS Lambda 핸들러.

Flask 앱을 AWS Lambda + API Gateway HTTP API(v2)에서 실행하기 위한 엔트리포인트.
HTTP API v2 페이로드를 REST API v1 형식으로 변환한 뒤 aws-wsgi에 전달한다.
"""

import awsgi
from dashboard.server import app


def _convert_v2_to_v1(event):
    """API Gateway HTTP API (v2) 이벤트를 REST API (v1) 형식으로 변환."""
    if "httpMethod" in event:
        # 이미 v1 형식이면 그대로 반환
        return event

    request_context = event.get("requestContext", {})
    http = request_context.get("http", {})

    v1_event = {
        "httpMethod": http.get("method", "GET"),
        "path": event.get("rawPath", "/"),
        "queryStringParameters": event.get("queryStringParameters"),
        "headers": event.get("headers", {}),
        "body": event.get("body"),
        "isBase64Encoded": event.get("isBase64Encoded", False),
        "requestContext": request_context,
    }
    return v1_event


def handler(event, context):
    """Lambda 핸들러 — API Gateway 프록시 통합용."""
    event = _convert_v2_to_v1(event)
    return awsgi.response(app, event, context, base64_content_types={"image/png", "image/jpeg"})
