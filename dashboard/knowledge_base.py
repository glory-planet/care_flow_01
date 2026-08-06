"""Bedrock Knowledge Base 연동 모듈.

S3에 저장된 재활 가이드라인 문서를 검색하여 챗봇에 컨텍스트로 제공한다.
Bedrock의 RetrieveAndGenerate API를 사용하거나,
단순히 S3에서 관련 문서를 읽어 Claude에게 컨텍스트로 전달한다.
"""

import boto3

REGION = "us-east-1"
KB_BUCKET = "careflow-kb-documents"
KB_PREFIX = "knowledge-base/"

_s3_client = None


def _get_s3():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=REGION)
    return _s3_client


def list_documents():
    """KB 버킷의 문서 목록을 반환한다."""
    s3 = _get_s3()
    response = s3.list_objects_v2(Bucket=KB_BUCKET, Prefix=KB_PREFIX)
    docs = []
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if key.endswith(".md"):
            docs.append(key)
    return docs


def get_document(key):
    """S3에서 문서 내용을 읽는다."""
    s3 = _get_s3()
    response = s3.get_object(Bucket=KB_BUCKET, Key=key)
    return response["Body"].read().decode("utf-8")


def search_relevant_documents(query, max_docs=3):
    """환자 질문에 관련된 문서를 키워드 기반으로 검색한다.

    단순 키워드 매칭으로 관련 문서를 찾는다.
    향후 Bedrock KB의 벡터 검색으로 업그레이드 가능.
    """
    docs = list_documents()
    query_lower = query.lower()

    # 키워드 매핑
    keyword_map = {
        "무릎": ["TKR", "관절", "스쿼트"],
        "어깨": ["회전근개", "어깨"],
        "뇌졸중": ["뇌졸중", "재활"],
        "낙상": ["낙상", "균형", "노인"],
        "당뇨": ["당뇨"],
        "고혈압": ["고혈압", "혈압"],
        "골다공증": ["골다공증", "뼈"],
        "항응고": ["항응고", "와파린"],
        "스트레칭": ["스트레칭", "운동"],
        "통증": ["통증", "운동가이드"],
    }

    # 쿼리에서 관련 키워드 찾기
    relevant_keywords = set()
    for key, keywords in keyword_map.items():
        if key in query_lower:
            relevant_keywords.update(keywords)

    # 관련 문서 필터링
    scored_docs = []
    for doc_key in docs:
        doc_name_lower = doc_key.lower()
        score = 0
        for keyword in relevant_keywords:
            if keyword.lower() in doc_name_lower:
                score += 1
        if score > 0:
            scored_docs.append((score, doc_key))

    # 점수순 정렬, 상위 max_docs개 반환
    scored_docs.sort(reverse=True)
    selected = [key for _, key in scored_docs[:max_docs]]

    # 매칭 없으면 일반 운동 원칙 문서 반환
    if not selected:
        for doc_key in docs:
            if "운동처방" in doc_key or "운동가이드" in doc_key:
                selected.append(doc_key)
                if len(selected) >= max_docs:
                    break

    # 문서 내용 로드
    results = []
    for key in selected:
        try:
            content = get_document(key)
            results.append({"key": key, "content": content})
        except Exception:
            continue

    return results


def build_rag_context(query):
    """챗봇에 전달할 RAG 컨텍스트를 생성한다."""
    docs = search_relevant_documents(query)
    if not docs:
        return ""

    context_parts = ["[참고 가이드라인]"]
    for doc in docs:
        # 문서 이름에서 파일명만 추출
        filename = doc["key"].split("/")[-1].replace(".md", "")
        content = doc["content"]
        # 너무 길면 잘라냄
        if len(content) > 2000:
            content = content[:2000] + "..."
        context_parts.append(f"\n--- {filename} ---\n{content}")

    return "\n".join(context_parts)
