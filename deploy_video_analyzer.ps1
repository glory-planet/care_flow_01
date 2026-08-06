# 영상 분석 Lambda (Container Image) 배포 스크립트
# 사전 조건: Docker Desktop 실행 중이어야 함

$ErrorActionPreference = "Stop"
$aws = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
$REGION = "us-east-1"
$ACCOUNT_ID = "769456250598"
$ECR_URI = "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"
$REPO_NAME = "careflow-video-analyzer"
$IMAGE_URI = "$ECR_URI/${REPO_NAME}:latest"
$FUNCTION_NAME = "CareFlow-VideoAnalyzer"

Write-Host "=== 1. ECR 로그인 ===" -ForegroundColor Cyan
& $aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URI

Write-Host "`n=== 2. Docker 이미지 빌드 ===" -ForegroundColor Cyan
docker build -t $REPO_NAME -f video_analysis_lambda/Dockerfile .

Write-Host "`n=== 3. 이미지 태그 + ECR 푸시 ===" -ForegroundColor Cyan
docker tag "${REPO_NAME}:latest" $IMAGE_URI
docker push $IMAGE_URI

Write-Host "`n=== 4. Lambda 함수 생성/업데이트 ===" -ForegroundColor Cyan
$functionExists = & $aws lambda get-function --function-name $FUNCTION_NAME --region $REGION 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Lambda 함수 생성 중..."
    & $aws lambda create-function `
        --function-name $FUNCTION_NAME `
        --package-type Image `
        --code "ImageUri=$IMAGE_URI" `
        --role "arn:aws:iam::${ACCOUNT_ID}:role/CareFlow-Lambda-Role" `
        --timeout 300 `
        --memory-size 1024 `
        --region $REGION
} else {
    Write-Host "Lambda 함수 업데이트 중..."
    & $aws lambda update-function-code `
        --function-name $FUNCTION_NAME `
        --image-uri $IMAGE_URI `
        --region $REGION
}

Write-Host "`n=== 5. S3 트리거 설정 ===" -ForegroundColor Cyan
# Lambda에 S3 호출 권한 부여
& $aws lambda add-permission `
    --function-name $FUNCTION_NAME `
    --statement-id s3-trigger `
    --action lambda:InvokeFunction `
    --principal s3.amazonaws.com `
    --source-arn "arn:aws:s3:::careflow-exercise-videos" `
    --region $REGION 2>$null

# S3 이벤트 알림 설정
$notification = @"
{
  "LambdaFunctionConfigurations": [
    {
      "LambdaFunctionArn": "arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${FUNCTION_NAME}",
      "Events": ["s3:ObjectCreated:Put"],
      "Filter": {
        "Key": {
          "FilterRules": [
            {"Name": "prefix", "Value": "videos/"},
            {"Name": "suffix", "Value": ".webm"}
          ]
        }
      }
    }
  ]
}
"@
$notification | Set-Content -Path "s3_notification.json"
& $aws s3api put-bucket-notification-configuration `
    --bucket careflow-exercise-videos `
    --notification-configuration file://s3_notification.json `
    --region $REGION
Remove-Item s3_notification.json -ErrorAction SilentlyContinue

Write-Host "`n=== 배포 완료! ===" -ForegroundColor Green
Write-Host "Lambda: $FUNCTION_NAME"
Write-Host "ECR: $IMAGE_URI"
Write-Host "트리거: S3 careflow-exercise-videos (videos/*.webm 업로드 시 자동 분석)"
