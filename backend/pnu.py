"""
주소 -> PNU(필지고유번호) 변환

카카오 로컬(Local) API의 주소 검색 결과에는 법정동코드(b_code), 본번(main_address_no),
부번(sub_address_no), 산 여부(mountain_yn)가 이미 포함되어 있어서, 별도의 "법정동코드
조회 API"를 한 번 더 부르지 않고도 바로 PNU를 조립할 수 있다.

PNU(19자리) 구성 규칙:
    법정동코드(10자리) + 산/일반 구분(1자리, 1=일반 2=산) + 본번(4자리) + 부번(4자리)

카카오 응답 필드는 Kakao Developers 공식 문서 기준(2026-09 확인):
https://developers.kakao.com/docs/latest/ko/local/dev-guide
"""

import requests

KAKAO_ADDRESS_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/address.json"


class AddressNotFoundError(Exception):
    pass


def search_address(query: str, kakao_rest_api_key: str) -> dict:
    """
    카카오 주소 검색 API를 호출해서 지번 주소 상세 정보를 돌려준다.
    도로명주소/지번주소 아무거나 입력해도 동작한다.
    """
    headers = {"Authorization": f"KakaoAK {kakao_rest_api_key}"}
    params = {"query": query, "analyze_type": "similar", "size": 1}
    try:
        res = requests.get(KAKAO_ADDRESS_SEARCH_URL, headers=headers, params=params, timeout=8)
        res.raise_for_status()
        data = res.json()
    except requests.exceptions.RequestException as e:
        raise AddressNotFoundError(f"카카오 주소 검색 서버 연결 실패: {e}")

    documents = data.get("documents", [])
    if not documents:
        raise AddressNotFoundError(f"주소를 찾을 수 없습니다: {query}")

    doc = documents[0]
    jibun = doc.get("address")  # 지번 주소 상세 (도로명 검색이어도 함께 내려옴)
    if not jibun:
        raise AddressNotFoundError(f"지번 주소 정보가 없는 결과입니다: {query}")

    return {
        "address_name": doc.get("address_name"),
        "road_address_name": (doc.get("road_address") or {}).get("address_name"),
        "x": doc.get("x"),  # 경도
        "y": doc.get("y"),  # 위도
        "b_code": jibun.get("b_code"),  # 법정동코드 10자리
        "main_address_no": jibun.get("main_address_no"),  # 본번
        "sub_address_no": jibun.get("sub_address_no"),  # 부번 (없으면 빈 문자열)
        "mountain_yn": jibun.get("mountain_yn"),  # "Y"/"N"
        "region_1depth_name": jibun.get("region_1depth_name"),
        "region_2depth_name": jibun.get("region_2depth_name"),
        "region_3depth_name": jibun.get("region_3depth_name"),
    }


def build_pnu(b_code: str, mountain_yn: str, main_address_no: str, sub_address_no: str) -> str:
    """지번 구성요소로 19자리 PNU를 조립한다."""
    if not b_code or len(b_code) != 10:
        raise ValueError(f"법정동코드(b_code)가 올바르지 않습니다: {b_code!r}")

    mountain_flag = "2" if (mountain_yn or "N").upper() == "Y" else "1"
    main_no = str(main_address_no or "0").zfill(4)
    sub_no = str(sub_address_no or "0").zfill(4)
    return f"{b_code}{mountain_flag}{main_no}{sub_no}"


def address_to_pnu(query: str, kakao_rest_api_key: str) -> dict:
    """주소 문자열 하나로 PNU와 부가 정보를 한 번에 얻는다."""
    info = search_address(query, kakao_rest_api_key)
    pnu = build_pnu(
        info["b_code"], info["mountain_yn"], info["main_address_no"], info["sub_address_no"]
    )
    info["pnu"] = pnu
    return info
