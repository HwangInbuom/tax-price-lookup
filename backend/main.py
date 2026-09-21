"""
주소 -> 공시가격 / 최근 실거래가 조회 백엔드 (프로토타입)

실행:
    pip install -r requirements.txt
    cp .env.example .env   # 키 값 채워넣기
    uvicorn main:app --reload --port 8000

테스트:
    curl "http://localhost:8000/lookup?address=서울특별시 마포구 상암동 1634"
    curl "http://localhost:8000/lookup?address=서울특별시 마포구 상암동 1634&dong=104&ho=402"
    curl "http://localhost:8000/trade-price?address=서울특별시 마포구 상암동 1634"
"""

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

try:
    # Render 등: backend/ 폴더 안에서 직접 실행되는 경우 (평범한 파일 import)
    from pnu import address_to_pnu, AddressNotFoundError
    from price_api import get_apartment_price, PriceLookupError
    from trade_price_api import get_recent_trades, get_trades_for_month, TradePriceLookupError
except ImportError:
    # Vercel 등: backend가 패키지(backend.main)로 import되는 경우
    from backend.pnu import address_to_pnu, AddressNotFoundError
    from backend.price_api import get_apartment_price, PriceLookupError
    from backend.trade_price_api import get_recent_trades, get_trades_for_month, TradePriceLookupError

load_dotenv()

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
VWORLD_API_KEY = os.getenv("VWORLD_API_KEY", "")
VWORLD_DOMAIN = os.getenv("VWORLD_DOMAIN", "localhost")
# 계산기가 "올해" 기준으로 삼는 연도(종부세 상승률 계산의 기준점과 맞춤).
PRICE_YEAR = os.getenv("PRICE_API_YEAR", "2026")
# 작년 공시가격 조회에 쓸 연도. 따로 지정하지 않으면 PRICE_YEAR-1을 자동으로 사용한다.
PREV_PRICE_YEAR = os.getenv("PRICE_API_PREV_YEAR", str(int(PRICE_YEAR) - 1))
DATA_GO_KR_SERVICE_KEY = os.getenv("DATA_GO_KR_SERVICE_KEY", "")

app = FastAPI(title="주택 공시가격 / 실거래가 조회 API")

# 계산기(프론트엔드)가 다른 origin에서 호출할 것이므로 CORS 허용.
# 운영 배포 시에는 allow_origins를 실제 프론트엔드 도메인으로 좁힐 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/lookup")
def lookup(
    address: str = Query(..., description="도로명 또는 지번 주소"),
    dong: str | None = Query(None, description="동명, 예: 104 (아파트 단지 내 특정 세대를 찾을 때)"),
    ho: str | None = Query(None, description="호명, 예: 402 (아파트 단지 내 특정 세대를 찾을 때)"),
):
    if not KAKAO_REST_API_KEY:
        raise HTTPException(500, "KAKAO_REST_API_KEY가 설정되지 않았습니다 (.env 확인)")
    if not VWORLD_API_KEY:
        raise HTTPException(500, "VWORLD_API_KEY가 설정되지 않았습니다 (.env 확인)")

    # 1) 주소 -> PNU
    try:
        addr_info = address_to_pnu(address, KAKAO_REST_API_KEY)
    except AddressNotFoundError as e:
        raise HTTPException(404, str(e))

    # 2) PNU(+동/호) -> 공동주택가격 (올해 기준)
    # 아파트/연립주택이 아닌 단독주택은 공식 오픈API가 없어 자동조회를 지원하지 않는다.
    # 이 경우 프론트엔드에서 "부동산공시가격알리미에서 직접 확인 후 입력" 안내로 전환할 것.
    try:
        price = get_apartment_price(
            addr_info["pnu"], PRICE_YEAR, VWORLD_API_KEY, VWORLD_DOMAIN, dong, ho
        )
    except PriceLookupError as e:
        return {
            "address": addr_info,
            "price": None,
            "price_year": PRICE_YEAR,
            "prev_price": None,
            "prev_price_year": PREV_PRICE_YEAR,
            "prev_price_message": None,
            "message": f"공동주택가격을 찾지 못했습니다 (단독주택이거나 데이터 미제공 가능): {e}",
        }

    # 동/호를 지정하지 않았는데 단지 내 세대가 여러 개 섞여 나온 경우, 프론트엔드가
    # 사용자에게 동/호 입력을 다시 요청할 수 있도록 힌트를 같이 내려준다.
    needs_unit_disambiguation = (not dong or not ho) and (price.get("matched_count") or 1) > 1

    # 3) 같은 세대 기준으로 작년 공시가격도 한 번 더 조회한다 (종부세 상승률 계산용).
    # 신축 등으로 작년 데이터가 아예 없을 수 있는데, 그 경우에도 올해 값 조회는 이미
    # 성공했으므로 요청 전체를 실패시키지 않고 prev_price만 null로 내려준다.
    prev_price = None
    prev_price_message = None
    try:
        prev_price = get_apartment_price(
            addr_info["pnu"], PREV_PRICE_YEAR, VWORLD_API_KEY, VWORLD_DOMAIN, dong, ho
        )
    except PriceLookupError as e:
        prev_price_message = f"작년({PREV_PRICE_YEAR}년) 공시가격을 찾지 못했습니다 (신축 등으로 데이터가 없을 수 있음): {e}"

    return {
        "address": addr_info,
        "price": price,
        "price_year": PRICE_YEAR,
        "prev_price": prev_price,
        "prev_price_year": PREV_PRICE_YEAR,
        "prev_price_message": prev_price_message,
        "needs_unit_disambiguation": needs_unit_disambiguation,
    }


@app.get("/trade-price")
def trade_price(
    address: str = Query(..., description="도로명 또는 지번 주소"),
    months: int = Query(6, ge=1, le=24, description="최근 몇 개월치를 조회할지"),
):
    """양도소득세 참고용 - 이 주소(지번)의 최근 실거래 내역을 보여준다.
    취득가액/양도가액을 대신 채워주는 게 아니라 '요즘 시세가 대략 이렇다'는 참고 정보다.
    """
    if not KAKAO_REST_API_KEY:
        raise HTTPException(500, "KAKAO_REST_API_KEY가 설정되지 않았습니다 (.env 확인)")
    if not DATA_GO_KR_SERVICE_KEY:
        raise HTTPException(500, "DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다 (.env 확인)")

    try:
        addr_info = address_to_pnu(address, KAKAO_REST_API_KEY)
    except AddressNotFoundError as e:
        raise HTTPException(404, str(e))

    lawd_cd = addr_info["b_code"][:5]  # 법정동코드 10자리 중 앞 5자리 = 시군구코드

    try:
        trades = get_recent_trades(
            addr_info["main_address_no"],
            addr_info["sub_address_no"],
            lawd_cd,
            months=months,
            service_key=DATA_GO_KR_SERVICE_KEY,
        )
    except TradePriceLookupError as e:
        return {"address": addr_info, "trades": [], "message": str(e)}

    if not trades:
        return {
            "address": addr_info,
            "trades": [],
            "message": f"최근 {months}개월 내 이 지번의 아파트 매매 실거래 내역이 없습니다.",
        }

    return {"address": addr_info, "trades": trades[:20], "count": len(trades)}


@app.get("/trade-price-at")
def trade_price_at(
    address: str = Query(..., description="도로명 또는 지번 주소"),
    year_month: str = Query(..., description="취득시기, YYYYMM 6자리 (예: 202103)"),
    window_months: int = Query(1, ge=0, le=3, description="취득시기 앞뒤로 몇 개월씩 더 찾아볼지"),
):
    """양도소득세 참고용 - '이때 취득했는데 얼마였는지 기억이 안 난다'는 경우를 위해,
    입력한 취득시기 전후의 같은 지번 실거래 내역을 보여준다. 역시 참고용 정보일 뿐,
    취득가액 입력칸을 자동으로 채우지는 않는다.
    """
    if not year_month.isdigit() or len(year_month) != 6:
        raise HTTPException(400, "year_month은 YYYYMM 6자리 형식이어야 합니다 (예: 202103)")
    if not KAKAO_REST_API_KEY:
        raise HTTPException(500, "KAKAO_REST_API_KEY가 설정되지 않았습니다 (.env 확인)")
    if not DATA_GO_KR_SERVICE_KEY:
        raise HTTPException(500, "DATA_GO_KR_SERVICE_KEY가 설정되지 않았습니다 (.env 확인)")

    try:
        addr_info = address_to_pnu(address, KAKAO_REST_API_KEY)
    except AddressNotFoundError as e:
        raise HTTPException(404, str(e))

    lawd_cd = addr_info["b_code"][:5]

    try:
        trades = get_trades_for_month(
            addr_info["main_address_no"],
            addr_info["sub_address_no"],
            lawd_cd,
            year_month,
            service_key=DATA_GO_KR_SERVICE_KEY,
            window=window_months,
        )
    except TradePriceLookupError as e:
        return {"address": addr_info, "trades": [], "message": str(e)}

    if not trades:
        return {
            "address": addr_info,
            "trades": [],
            "message": f"{year_month} 전후 {window_months}개월 내 이 지번의 실거래 내역이 없습니다.",
        }

    return {"address": addr_info, "trades": trades[:20], "count": len(trades)}


@app.get("/health")
def health():
    return {"ok": True}
