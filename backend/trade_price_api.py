"""
아파트 매매 실거래가 조회 (양도소득세 참고 시세용)

*** 검증 완료 (2026-09-17) ***
국토교통부_아파트 매매 실거래가 상세 자료. data.go.kr가 직접 호스팅하는 API로,
(브이월드로 연결되는 공동주택가격과 달리) data.go.kr 계정에 로그인해서 상세페이지에
들어가는 순간 "개발계정"이 즉시 승인되어 별도 신청 절차 없이 바로 쓸 수 있었다.

요청 예시:
    GET https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev
        ?serviceKey=발급받은인증키
        &LAWD_CD=11440        (시군구코드 5자리 = 법정동코드 10자리의 앞 5자리)
        &DEAL_YMD=202507      (계약년월 YYYYMM, 한 달 단위로만 조회 가능)
        &numOfRows=1000
        &pageNo=1

실제 응답은 XML이며(JSON 파라미터 없음), response/header에 resultCode="000"이면 정상.
response/body/items/item 이 실거래 1건씩이고 주요 필드:
    aptNm(단지명), aptDong(동, 비어있을 수 있음), bonbun/bubun(지번 - PNU의 본번/부번과
    동일한 4자리 zero-padded 규칙), dealAmount(거래금액, "144,000" 같은 만원 단위 문자열),
    dealYear/dealMonth/dealDay, excluUseAr(전용면적 m2), floor(층), umdNm(읍면동명)

이 API는 "그 지번(단지)의 그 달 거래 전체"를 돌려주는 방식이라, 특정 주소의 최근 시세를
보려면 여러 달을 돌려가며 모은 다음 bonbun/bubun(=PNU의 본번/부번)이 일치하는 것만
걸러내야 한다. 아래 get_recent_trades()가 그 역할을 한다.

주의: 이건 "참고 시세"일 뿐이다. 양도소득세 계산에 들어가는 취득가액/양도가액은 사용자
본인이 실제로 계약한 금액이라 이 API로 대신 알아낼 수 없다 (공시가격과는 성격이 다름).
"""

import xml.etree.ElementTree as ET
from datetime import date

import requests

BASE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"


class TradePriceLookupError(Exception):
    pass


def _recent_year_months(n):
    """오늘부터 거슬러 올라가는 YYYYMM 문자열 n개를 반환한다."""
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append("%04d%02d" % (y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return out


def fetch_trades_raw(lawd_cd: str, deal_ymd: str, service_key: str) -> str:
    """특정 시군구·계약월의 실거래 전체를 XML 원문 그대로 가져온다."""
    params = {
        "serviceKey": service_key,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    res = requests.get(BASE_URL, params=params, timeout=8)
    res.raise_for_status()
    return res.text


def _parse_items(xml_text: str):
    root = ET.fromstring(xml_text)
    result_code = root.findtext("./header/resultCode")
    if result_code not in (None, "000", "00"):
        msg = root.findtext("./header/resultMsg") or result_code
        raise TradePriceLookupError(f"국토교통부 API 오류: {msg}")

    items = []
    for item in root.findall("./body/items/item"):
        row = {child.tag: (child.text or "").strip() for child in item}
        items.append(row)
    return items


def get_recent_trades(
    main_address_no: str,
    sub_address_no: str,
    lawd_cd: str,
    months: int = 6,
    service_key: str = None,
):
    """PNU의 본번/부번과 같은 지번(bonbun/bubun)의 최근 N개월 실거래 내역을 모아서 반환한다."""
    target_bonbun = str(main_address_no or "0").zfill(4)
    target_bubun = str(sub_address_no or "0").zfill(4)

    matched = []
    for ymd in _recent_year_months(months):
        try:
            raw = fetch_trades_raw(lawd_cd, ymd, service_key)
        except requests.RequestException:
            continue  # 그 달 조회 실패는 건너뛰고 나머지 달은 계속 시도
        for row in _parse_items(raw):
            if row.get("bonbun") == target_bonbun and row.get("bubun") == target_bubun:
                matched.append(_row_to_trade(row))

    matched.sort(key=lambda r: r["deal_date"], reverse=True)
    return matched


def _row_to_trade(row: dict) -> dict:
    amount_str = (row.get("dealAmount") or "").replace(",", "")
    return {
        "apt_name": row.get("aptNm"),
        "dong": (row.get("aptDong") or "").strip() or None,
        "floor": row.get("floor"),
        "area_m2": row.get("excluUseAr"),
        "deal_date": "%s-%s-%s" % (
            row.get("dealYear"),
            (row.get("dealMonth") or "").zfill(2),
            (row.get("dealDay") or "").zfill(2),
        ),
        "price_won": int(amount_str) * 10000 if amount_str.isdigit() else None,
        "dealing_type": row.get("dealingGbn"),
    }


def _months_around(year_month: str, window: int):
    """year_month(YYYYMM) 앞뒤로 window개월씩, 오래된 순으로 반환한다."""
    y, m = int(year_month[:4]), int(year_month[4:6])
    out = []
    for offset in range(-window, window + 1):
        yy, mm = y, m + offset
        while mm < 1:
            mm += 12
            yy -= 1
        while mm > 12:
            mm -= 12
            yy += 1
        out.append("%04d%02d" % (yy, mm))
    return out


def get_trades_for_month(
    main_address_no: str,
    sub_address_no: str,
    lawd_cd: str,
    year_month: str,
    service_key: str = None,
    window: int = 1,
):
    """특정 취득시기(YYYYMM) 전후 window개월 동안, 같은 지번의 실거래 내역을 모아서 반환한다.
    "이때 취득했는데 얼마였는지 기억이 안 난다"는 경우를 위한 참고용 조회다.
    """
    target_bonbun = str(main_address_no or "0").zfill(4)
    target_bubun = str(sub_address_no or "0").zfill(4)

    matched = []
    for ymd in _months_around(year_month, window):
        try:
            raw = fetch_trades_raw(lawd_cd, ymd, service_key)
        except requests.RequestException:
            continue
        for row in _parse_items(raw):
            if row.get("bonbun") == target_bonbun and row.get("bubun") == target_bubun:
                matched.append(_row_to_trade(row))

    matched.sort(key=lambda r: r["deal_date"])  # 오래된 순 (취득시기에 가까운 순서로 보기 편하게)
    return matched
