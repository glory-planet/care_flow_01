"""병원 정보(가짜 EMR) RAG 조회.

환자 등록 화면에서 주치의가 "고유 ID"(5자리 숫자)를 입력하면, 이 모듈이 S3 Vectors에
심어둔 데모 병원 데이터에서 해당 ID의 환자 정보(이름/나이/진단명/관절)를 조회해서
자동완성에 쓴다.

설계 노트 (2026-08-06): 순수 텍스트 임베딩 유사도만으로는 숫자로만 된 ID를 안정적으로
구분하기 어렵다 ("10234"와 "10235"는 벡터 공간에서 거의 동일하게 임베딩될 위험이 있음).
그래서 검색은 벡터 유사도가 아니라 S3 Vectors의 메타데이터 정확 필터(filter)로 한다 —
벡터 자체는 이름+진단명 텍스트를 Titan으로 임베딩한 것을 저장해두지만(형식상 "진짜 RAG"
구조를 갖추기 위함), 실제 조회는 `unique_id` 메타데이터의 정확 일치로 수행해서 데모를
여러 번 반복해도 항상 같은 결과가 나오게 한다.
"""

import boto3

VECTOR_BUCKET = "careflow-hospital-rag"
VECTOR_INDEX = "patients"
EMBED_MODEL_ID = "amazon.titan-embed-text-v2:0"
REGION = "us-east-1"

_bedrock_client = None
_s3vectors_client = None


def _get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=REGION)
    return _bedrock_client


def _get_s3vectors_client():
    global _s3vectors_client
    if _s3vectors_client is None:
        _s3vectors_client = boto3.client("s3vectors", region_name=REGION)
    return _s3vectors_client


def embed_text(text):
    """Titan Embed Text v2로 텍스트를 1024차원 벡터로 변환한다."""
    import json

    client = _get_bedrock_client()
    response = client.invoke_model(
        modelId=EMBED_MODEL_ID,
        contentType="application/json",
        body=json.dumps({"inputText": text}),
    )
    body = json.loads(response["body"].read())
    return body["embedding"]


def seed_patient_vector(unique_id, name, age, diagnosis, joint):
    """데모 병원 데이터 한 명을 S3 Vectors에 심는다 (시드 스크립트 전용)."""
    client = _get_s3vectors_client()
    text = f"{name} {age}세 {diagnosis}"
    vector = embed_text(text)
    client.put_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        vectors=[
            {
                "key": unique_id,
                "data": {"float32": vector},
                "metadata": {
                    "unique_id": unique_id,
                    "name": name,
                    "age": age,
                    "diagnosis": diagnosis,
                    "joint": joint,
                },
            }
        ],
    )


def lookup_patient_by_unique_id(unique_id):
    """고유 ID(5자리 숫자 문자열)로 병원 데모 데이터를 정확히 조회한다.

    벡터 유사도가 아니라 메타데이터 정확 필터로 검색하므로 결과가 항상 결정적이다.
    매칭되는 환자가 없으면 None을 반환한다.
    """
    client = _get_s3vectors_client()
    # cosine distance 인덱스는 영벡터를 허용하지 않으므로, 필터가 실질적인 검색을
    # 담당하는 이 조회에서는 임의의 정규화되지 않은 더미 벡터를 넣는다 (값 자체는 무관).
    dummy_vector = [1.0] + [0.0] * 1023
    response = client.query_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        topK=1,
        queryVector={"float32": dummy_vector},
        filter={"unique_id": unique_id},
        returnMetadata=True,
        returnDistance=False,
    )
    results = response.get("vectors", [])
    if not results:
        return None
    metadata = results[0]["metadata"]
    return {
        "unique_id": metadata["unique_id"],
        "name": metadata["name"],
        "age": metadata["age"],
        "diagnosis": metadata["diagnosis"],
        "joint": metadata["joint"],
    }
