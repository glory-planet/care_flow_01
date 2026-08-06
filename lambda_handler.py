"""AWS Lambda 핸들러.

Flask 앱을 AWS Lambda + API Gateway에서 실행하기 위한 엔트리포인트.
aws-wsgi 라이브러리를 사용해 API Gateway 이벤트를 WSGI 요청으로 변환한다.
"""

import awsgi
from dashboard.server import app


def handler(event, context):
    """Lambda 핸들러 — API Gateway 프록시 통합용."""
    return awsgi.response(app, event, context, base64_content_types={"image/png", "image/jpeg"})
