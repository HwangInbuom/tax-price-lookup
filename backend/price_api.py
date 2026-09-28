"""
PNU -> 공동주택가격(공시가격) 조회

*** 검증 완료 (2026-09-17) ***
국토교통부 "공동주택가격정보"는 공공데이터포털(data.go.kr)에서는 활용신청만 하고,
실제 API 호출은 브이월드(V-World, api.vworld.kr)의 "국가중점데이터 API"로 이루어진다.
아래 BASE_URL / 파라미터 / 응답 필드명은 사용자가 실제로 브이월드 인증키를 발급받아
브라우저에서 직접 호출해본 응답을 그대로 기준으로 작성했다 (더 이상 추측/placeholder 아님).

요청 예시:
    http://api.vworld.kr/ned/data/getApartHousingPriceAttr
        ?key=발급받은인증키
        &domain=발급신청시등록한도메인
        &pnu=1144012700116340000
        &stdrYear=2025
        &format=json
        &numOfRows=100
        &pageNo=1
        &dongNm=104   (선택, 동명)
        &hoNm=402     (선택, 호명)

실제 응답 예시(축약):
    {
      "apartHousingPrices": {
        "field": [
          {
            "stdrYear": "2025", "pnu": "1144012700116340000",
            "aphusNm": "상암월드컵파크1단지", "dongNm": "104", "hoNm": "402",
            "floorNm": "4", "prvuseAr": "49.53",
            "pblntfPc": "279000000",   <- 공시가격(원 단위)
            "lastUpdtDt": "2025-08-05", ...
          },
          ...
        ],
        "totalCount": "1640", "numOfRows": "10", "pageNo": "1",
        "resultCode": "", "resultMsg": ""
      }
    }

주의: 아파트 한 단지(=하나의 PNU)에는 동·호가 매우 많다(위 예시 단지만 1,640건).
dongNm/hoNm을 지정하지 않으면 여러 세대가 섞여서 돌아오므로, 특정 세대의 정확한
공시가격을 원하면 dongNm/hoNm까지 함께 넘겨서 필터링해야 한다. (일반 사용자 입장에서는
"동/호수"를 프론트엔드에서 별도 입력받아야 한다는 뜻 — 도로명주소만으로는 동/호까지
특정할 수 없다.)
"""

import requests

try:
    # 브이월드 앞단이 TLS 지문(JA3)으로 브라우저가 아닌 클라이언트를 걸러내는 것으로 보인다.
    # curl_cffi 는 실제 크롬과 같은 TLS/HTTP2 지문으로 호출해 준다. 없으면 requests 만 쓴다.
    from curl_cffi import requests as cffi
except Exception:  # pragma: no cover
    cffi = None

PATH = "/ned/data/getApartHousingPriceAttr"
# 브이월드가 서버 쪽 https 호출에 응답 없이 연결을 끊는 경우가 있어서 https -> http 순으로 시도한다.
# (브이월드 공식 예제와 문서가 http 주소를 쓴다.)
BASE_URLS = ["https://api.vworld.kr" + PATH, "http://api.vworld.kr" + PATH]
BASE_URL = BASE_URLS[0]  # 이전 코드 호환용

# requests 기본 User-Agent(python-requests/x.y)를 막는 공공기관 서버가 많아서 브라우저 UA를 쓴다.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


class PriceLookupError(Exception):
    pass


def _referer_header(vworld_domain: str) -> str | None:
    """브이월드는 domain 쿼리 파라미터뿐 아니라, 실제 HTTP Referer 헤더까지
    등록된 도메인과 일치하는지 함께 검사하는 것으로 확인되었다 (2026-09-21).
    서버 대 서버(백엔드) 호출은 브라우저가 아니라서 Referer 헤더가 원래 비어
    있는데, 이게 브이월드 쪽에서 비정상 요청으로 간주되어 연결 자체를 끊어버리는
    것으로 보인다. domain 파라미터로 등록한 도메인을 그대로 Referer로도 실어
    보낸다."""
    domain = (vworld_domain or "").strip()
    if not domain:
        return None
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain if domain.endswith("/") else domain + "/"
    return f"https://{domain}/"


def fetch_apartment_price_raw(
    pnu: str,
    year: str,
    vworld_key: str,
    vworld_domain: str,
    dong_nm: str | None = None,
    ho_nm: str | None = None,
) -> dict:
    """브이월드 공동주택가격속성조회 API를 호출해서 원본 응답(dict)을 그대로 반환한다."""
    params = {
        "key": vworld_key,
        "domain": vworld_domain,
        "pnu": pnu,
        "stdrYear": year,
        "format": "json",
        "numOfRows": 100,  # 한 단지에 세대가 많을 수 있어 넉넉히 요청
        "pageNo": 1,
    }
    if dong_nm:
        params["dongNm"] = dong_nm
    if ho_nm:
        params["hoNm"] = ho_nm

    referer = _referer_header(vworld_domain)

    plain_headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Connection": "close",  # keep-alive 협상 단계에서 끊기는 것을 피한다
    }
    # impersonate 를 쓰면 curl_cffi 가 크롬의 헤더 전체를 알아서 넣으므로 Referer 만 얹는다.
    cffi_headers = {}
    if referer:
        plain_headers["Referer"] = referer
        cffi_headers["Referer"] = referer

    attempts = []
    if cffi is not None:
        for url in BASE_URLS:
            scheme = url.split(":", 1)[0]
            attempts.append(
                (
                    f"chrome({scheme})",
                    lambda u=url: cffi.get(
                        u, params=params, headers=cffi_headers, timeout=10, impersonate="chrome"
                    ),
                )
            )
    else:
        attempts.append(("chrome", None))  # 설치 안 됨을 실패 목록에 남기기 위한 자리
    for url in BASE_URLS:
        scheme = url.split(":", 1)[0]
        attempts.append((f"requests({scheme})", lambda u=url: requests.get(u, params=params, headers=plain_headers, timeout=8)))

    # 어느 방식/주소에서 어떻게 실패했는지 전부 남긴다. 다음 실패를 바로 진단하기 위한 것.
    failures = []
    for label, call in attempts:
        if call is None:
            failures.append(f"{label}: curl_cffi 미설치")
            continue
        res = None
        try:
            res = call()
            res.raise_for_status()
            return res.json()
        except Exception as e:
            body = ""
            try:
                if res is not None and res.text:
                    body = " 본문=" + res.text[:150].replace("\n", " ")
            except Exception:
                pass
            failures.append(f"{label}: {type(e).__name__} {e}{body}")

    # (브이월드는 클라우드 서버에서 오는 호출에 502 를 돌려주는 것이 2026-09-28 확인됨.
    #  같은 키·같은 주소를 사용자 PC 브라우저에서 부르면 정상 응답한다.)
    raise PriceLookupError("브이월드 서버 연결 실패 — " + " / ".join(failures))


def parse_price(raw: dict, dong_nm: str | None = None, ho_nm: str | None = None) -> dict:
    """실제 확인된 응답 포맷(apartHousingPrices.field)에서 공시가격을 꺼낸다."""
    body = raw.get("apartHousingPrices") or {}

    result_code = body.get("resultCode")
    if result_code and result_code not in ("", "00"):
        raise PriceLookupError(f"브이월드 API 오류: {body.get('resultMsg') or result_code}")

    items = body.get("field") or []
    if not items:
        raise PriceLookupError("해당 PNU/연도에 대한 공시가격 데이터가 없습니다.")

    # dongNm/hoNm을 API 파라미터로 넘겼어도, 한 번 더 클라이언트 쪽에서도 확인해서 좁힌다.
    candidates = items
    if dong_nm and ho_nm:
        narrowed = [it for it in items if it.get("dongNm") == dong_nm and it.get("hoNm") == ho_nm]
        if narrowed:
            candidates = narrowed

    item = candidates[0]
    if "pblntfPc" not in item:
        return {
            "price_won": None,
            "raw_item": item,
            "note": "pblntfPc 필드를 찾지 못했습니다. raw_item을 확인하세요.",
        }

    return {
        "price_won": int(str(item["pblntfPc"]).replace(",", "")),
        "apt_name": item.get("aphusNm"),
        "dong": item.get("dongNm"),
        "ho": item.get("hoNm"),
        "floor": item.get("floorNm"),
        "area_m2": item.get("prvuseAr"),
        "std_year": item.get("stdrYear"),
        "last_updated": item.get("lastUpdtDt"),
        "matched_count": len(candidates),
        "total_units_in_complex": body.get("totalCount"),
        "raw_item": item,
    }


def get_apartment_price(
    pnu: str,
    year: str,
    vworld_key: str,
    vworld_domain: str,
    dong_nm: str | None = None,
    ho_nm: str | None = None,
) -> dict:
    raw = fetch_apartment_price_raw(pnu, year, vworld_key, vworld_domain, dong_nm, ho_nm)
    return parse_price(raw, dong_nm, ho_nm)
