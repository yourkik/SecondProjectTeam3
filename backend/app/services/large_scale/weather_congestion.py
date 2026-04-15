import json
import urllib.parse
import urllib.request
from datetime import datetime

from app.core.config import settings


def _first_non_empty(item, keys, default=""):
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip() != "":
            return str(value)
    return default


def _extract_disaster_rows(data):
    if not isinstance(data, dict):
        return []

    disaster_msg = data.get("DisasterMsg")

    if isinstance(disaster_msg, dict):
        if isinstance(disaster_msg.get("row"), list):
            return disaster_msg["row"]

        body = disaster_msg.get("body")
        if isinstance(body, dict):
            items = body.get("items")
            if isinstance(items, list):
                return items
            if isinstance(items, dict):
                if isinstance(items.get("item"), list):
                    return items["item"]
                if isinstance(items.get("item"), dict):
                    return [items["item"]]

    if isinstance(disaster_msg, list):
        for chunk in disaster_msg:
            if not isinstance(chunk, dict):
                continue
            if isinstance(chunk.get("row"), list):
                return chunk["row"]

            body = chunk.get("body")
            if isinstance(body, dict):
                items = body.get("items")
                if isinstance(items, list):
                    return items
                if isinstance(items, dict):
                    if isinstance(items.get("item"), list):
                        return items["item"]
                    if isinstance(items.get("item"), dict):
                        return [items["item"]]

    response = data.get("response")
    if isinstance(response, dict):
        body = response.get("body")
        if isinstance(body, dict):
            items = body.get("items")
            if isinstance(items, list):
                return items
            if isinstance(items, dict):
                if isinstance(items.get("item"), list):
                    return items["item"]
                if isinstance(items.get("item"), dict):
                    return [items["item"]]

    body = data.get("body")
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        items = body.get("items")
        if isinstance(items, list):
            return items
        if isinstance(items, dict):
            if isinstance(items.get("item"), list):
                return items["item"]
            if isinstance(items.get("item"), dict):
                return [items["item"]]

    return []


def fetch_city_data(area_name: str):
    """
    서울 실시간 도시 데이터 API 통신 함수.
    주어진 장소 이름(area_name)으로 날씨 및 혼잡도 정보를 가져온다.
    """
    try:
        encoded_area = urllib.parse.quote(area_name)
        url = f"http://openapi.seoul.go.kr:8088/{settings.SEOUL_CITY_API_KEY}/json/citydata/1/5/{encoded_area}"

        req = urllib.request.Request(url)
        res = urllib.request.urlopen(req, timeout=3)
        data = json.loads(res.read().decode("utf-8"))

        if "CITYDATA" in data:
            return data["CITYDATA"]
        return None
    except Exception as e:
        print(f"CityData API Error for {area_name}: {e}")
        return None


def fetch_disaster_messages():
    """
    재난안전데이터공유플랫폼의 행정안전부 긴급재난문자 OpenAPI를 조회한다.
    오늘 날짜 기준 최신 재난문자만 가져오며, 응답 구조 변화도 최대한 흡수한다.
    """
    if settings.DISASTER_API_KEY == "PLEASE_ENTER_YOUR_API_KEY_HERE":
        return [{
            "sn": "1",
            "crt_dt": "방금",
            "msg_cn": "[테스트] API 키가 입력되지 않았습니다. .env 값을 확인하세요.",
            "rcptn_rgn_nm": "서울 강동구",
            "emrg_step_nm": "안전안내",
            "dst_se_nm": "안내",
        }]

    try:
        url = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247"
        params = {
            "serviceKey": settings.DISASTER_API_KEY,
            "pageNo": "1",
            "numOfRows": "10",
            "returnType": "json",
            "crtDt": datetime.now().strftime("%Y%m%d"),
        }

        query_string = urllib.parse.urlencode(params)
        req = urllib.request.Request(url + "?" + query_string)
        res = urllib.request.urlopen(req, timeout=5)
        data = json.loads(res.read().decode("utf-8"))

        results = []
        for item in _extract_disaster_rows(data):
            if not isinstance(item, dict):
                continue

            results.append({
                "sn": _first_non_empty(item, ["SN", "sn", "id", "msgSn"]),
                "crt_dt": _first_non_empty(item, ["CRT_DT", "create_date", "crt_dt", "createDate", "sendDate"]),
                "msg_cn": _first_non_empty(item, ["MSG_CN", "msg", "msg_cn", "message", "contents"]),
                "rcptn_rgn_nm": _first_non_empty(item, ["RCPTN_RGN_NM", "location_name", "rcptn_rgn_nm", "regionName", "areaNm"]),
                "emrg_step_nm": _first_non_empty(item, ["EMRG_STEP_NM", "emrg_step_nm", "send_platform", "emergencyStepNm", "className"]),
                "dst_se_nm": _first_non_empty(item, ["DST_SE_NM", "dst_se_nm", "disaster_type", "disasterType", "category", "send_platform"]),
            })

        return results
    except Exception as e:
        print(f"Disaster Message API Error: {e}")
        return []
