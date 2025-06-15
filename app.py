import streamlit as st
import requests
import os
import base64
import openai
from openai import OpenAI
from deep_translator import GoogleTranslator

# ✅ 환경변수 로드
GOOGLE_API_KEY= st.secrets["GOOGLE_API_KEY"]
GOOGLE_TRANSLATE_API_KEY= st.secrets["GOOGLE_TRANSLATE_API_KEY"]
OPENAI_API_KEY= st.secrets["OPENAI_API_KEY"]
PASTEBIN_API_KEY= st.secrets["PASTEBIN_API_KEY"]

# ✅ 기본 설정
st.set_page_config(page_title="PlaceLog.AI", layout="wide")

# ✅ 로고 및 스타일
st.markdown("""
<div style='text-align: center;'>
  <h1 style='color: white; font-size: 48px;'>📍 PlaceLog.AI</h1>
  <p style='color: gray; font-size: 20px;'>사진 또는 장소명으로 공간을 분석하고 추천합니다</p>
</div>
""", unsafe_allow_html=True)

# ✅ 장소 세부 정보 가져오기
print("🔑 GOOGLE_API_KEY:", GOOGLE_API_KEY)
def get_place_details(place_name):
    findplace_url = "https://maps.googleapis.com/maps/api/place/findplacefromtext/json"
    detail_url = "https://maps.googleapis.com/maps/api/place/details/json"
    photo_url = "https://maps.googleapis.com/maps/api/place/photo"

    findplace_params = {
        "input": place_name,
        "inputtype": "textquery",
        "fields": "place_id,formatted_address",
        "language": "ko",
        "key": GOOGLE_API_KEY
    }

    response = requests.get(findplace_url, params=findplace_params).json()
    print("🔎 findplace response:", response)  # ✅ 이 줄도 추가!

    if not response.get("candidates"):
        return None

    place_id = response["candidates"][0]["place_id"]
    detail_params = {
        "place_id": place_id,
        "fields": "name,formatted_address,rating,photos,reviews,geometry",
        "language": "ko",
        "key": GOOGLE_API_KEY
    }

    # ✅ 여기에 디버깅용 print 추가
    details = requests.get(detail_url, params=detail_params)
    details_json = details.json()
    print("🧾 detail response:", details_json)  # ⭐ 터미널에 이게 뜹니다

    if details_json["status"] != "OK":
        return None

    result = details_json["result"]

    if "photos" in result:
        photo_urls = []
        for photo in result["photos"][:3]:
            ref = photo["photo_reference"]
            photo_urls.append(f"{photo_url}?maxwidth=800&photoreference={ref}&key={GOOGLE_API_KEY}")
        result["photo_urls"] = photo_urls

    return result


# ✅ 리뷰 번역
# 기존 함수는 텍스트만 번역하고 반환했습니다
# 아래처럼 수정하면 번역 결과와 작성자 정보, 별점, 작성 시점을 함께 묶어 반환합니다

def translate_reviews(reviews):
    try:
        results = []
        for r in reviews[:5]:  # ✅ 5개로 확장
            text = r.get("text", "")
            if text.strip():
                translated = GoogleTranslator(source='auto', target='ko').translate(text)
                results.append({
                    "author": r.get("author_name", "익명"),
                    "rating": r.get("rating", "N/A"),
                    "time": r.get("relative_time_description", ""),
                    "text": translated
                })
        return results if results else [{"text": "번역된 리뷰가 없습니다."}]
    except:
        return [{"text": "번역 실패"} for _ in range(5)]

client = OpenAI(api_key=OPENAI_API_KEY)
# ✅ 공간 개요 생성

def generate_summary(place):
    prompt = (
        f"장소 이름: {place['name']}\n"
        f"주소: {place['formatted_address']}\n"
        f"이 장소는 어떤 느낌의 공간인지, 분위기, 주변 특징 등을 고려해서 감성적이고 풍부한 한국어 설명을 작성해 주세요.\n"
    )
  
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )
    
        return response.choices[0].message.content.strip()
  
    except Exception as e:
        st.error(f"공간 개요를 불러오는 중 오류가 발생했습니다: {e}")
        return "⚠️ 공간 개요 생성 실패"

def generate_similar_places(place):
    prompt = f"""
    다음 장소와 비슷한 장소를 한국 또는 해외 유명 장소 중에 3곳 추천해 주세요.

    장소 이름: {place['name']}
    주소: {place['formatted_address']}
    설명: {st.session_state.get('summary', '')}

    장소 이름만 굵게 강조해서 3개 추천해주세요.
    """

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        st.error(f"공간 개요를 불러오는 중 오류가 발생했습니다: {e}")
        return "⚠️ 공간 개요 생성 실패"

# ✅ Pastebin 공유
def create_paste(content):
    paste_url = "https://pastebin.com/api/api_post.php"
    payload = {
        "api_dev_key": PASTEBIN_API_KEY,
        "api_option": "paste",
        "api_paste_code": content,
        "api_paste_private": 1
    }
    response = requests.post(paste_url, data=payload)
    return response.text

# ✅ 사용자 입력
place_input = st.text_input("📍 장소명을 입력하세요", "")
image_input = st.file_uploader("또는 공간 사진을 업로드하세요", type=["jpg", "png"])

# ✅ 분석 버튼
if "analyzed" not in st.session_state:
    st.session_state["analyzed"] = False
if "recommend_clicked" not in st.session_state:
    st.session_state["recommend_clicked"] = False
if "save_clicked" not in st.session_state:
    st.session_state["save_clicked"] = False

# 분석 버튼
if st.button("🔍 분석 시작"):
    st.session_state["analyzed"] = True
    st.session_state["recommend_clicked"] = False
    st.session_state["save_clicked"] = False

# 분석된 결과 표시
if st.session_state.get("analyzed", False) and place_input:
    place = get_place_details(place_input)

    if place:
        st.markdown(f"## 📌 {place['name']}")
        st.markdown(f"**주소:** [{place['formatted_address']}](https://www.google.com/maps/search/?api=1&query={place['formatted_address']})")
        lat = place["geometry"]["location"]["lat"]
        lng = place["geometry"]["location"]["lng"]
        map_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
        st.markdown(f"**🗺️ 지도에서 보기:** [Google Maps 링크]({map_url})")
        st.markdown(f"**⭐ 평점:** {place.get('rating', 'N/A')}")

        # 사진 출력
        if "photo_urls" in place:
            st.markdown("### 🖼️ 공간 사진")
            cols = st.columns(3)
            for i, url in enumerate(place["photo_urls"]):
                cols[i % 3].image(url, use_container_width=True)

        # 공간 설명
        with st.spinner("공간 설명 생성 중..."):
            try:
                summary = generate_summary(place)
                st.session_state["summary"] = summary
                st.markdown("### 🧠 공간 개요")
                st.write(summary)
            except:
                st.warning("⚠️ 공간 개요를 불러오는 데 문제가 발생했습니다.")

        # 리뷰
        with st.expander("💬 사용자 리뷰 보기"):
           if "reviews" in place:
               reviews_raw = place["reviews"]
               if len(reviews_raw) < 3:
                   st.warning("📉 리뷰 수가 적어 정확한 판단이 어려울 수 있습니다.")
               reviews_ko = translate_reviews(reviews_raw)
               st.session_state["reviews_ko"] = reviews_ko
               for r in reviews_ko:
                   st.markdown(f"""**👤 {r.get('author', '익명')}**  
               ⭐ {r.get('rating', 'N/A')}점 · 🕒 {r.get('time', '')}  
               > {r.get('text', '')}
               """)


           else:
               st.write("사용자 리뷰가 등록되지 않았습니다.")

        # ✅ 유사 장소 추천 바로 실행
        if st.button("🔁 유사한 장소 추천받기"):
            with st.spinner("유사 장소 추천 중..."):
                try:
                    suggestions = generate_similar_places(place)
                    st.session_state["suggestions"] = suggestions
                except:
                    st.session_state["suggestions"] = "⚠️ 추천 실패"

        if st.session_state.get("suggestions"):
           with st.expander("🧭 추천 결과 보기"):
               st.write(st.session_state["suggestions"])

        # ✅ 결과 저장 및 공유 버튼 클릭 시 바로 처리
        if st.button("💾 결과 저장 및 공유"):
            summary_saved = st.session_state.get("summary", "")
            reviews_saved = st.session_state.get("reviews_ko", [])

            # ✅ 딕셔너리 리스트인 리뷰를 문자열로 정리
            reviews_text = ""
            for r in reviews_saved:
                reviews_text += f"{r.get('author', '익명')} ⭐ {r.get('rating', 'N/A')}점 · {r.get('time', '')}\n{r.get('text', '')}\n\n"

            content = f"{place['name']}\n{place['formatted_address']}\n\n[공간 개요]\n{summary_saved}\n\n[리뷰]\n{reviews_text}"

            url = create_paste(content)
            st.success(f"✅ 공유 링크: [Pastebin 결과 보기]({url})")


    else:
        st.error("❌ 장소를 찾을 수 없습니다.")
elif image_input:
    st.info("""
📷 **사진 기반 AI 분석 기능 안내**

현재는 사진 업로드만으로 자동 분석은 제공되지 않습니다.  
하지만 앞으로는:

- 업로드한 사진을 분석해 자동으로 **장소를 인식하고**,  
- AI가 공간 개요 및 리뷰 요약을 자동 생성하는 기능이 추가될 예정입니다.

지금은 **사진 속 장소명을 직접 입력해보세요!**
""")
else:
    st.error("⚠️ 장소명 또는 사진을 입력해주세요.")
