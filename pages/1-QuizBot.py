import streamlit as st
import json
import wikipediaapi
import os
from openai import OpenAI


MY_OPENAI_API_KEY = os.getenv("MY_OPENAI_API_KEY")
QUIZBOT_ASSISTANT_ID = os.getenv("QUIZBOT_ASSISTANT_ID")
QUIZBOT_VECTOR_STORE_ID = os.getenv("QUIZBOT_VECTOR_STORE_ID")
LM_ASSITAINT_ID = os.getenv("LM_ASSISTANT_ID")  # LearningMate 어시스턴트 ID
LM_THREAD_ID = os.getenv("LM_THREAD_ID")  # LearningMate 쓰레드 ID

client = OpenAI(api_key=MY_OPENAI_API_KEY)
quiz_bot = client.beta.assistants.retrieve(assistant_id=QUIZBOT_ASSISTANT_ID)
learning_mate = client.beta.assistants.retrieve(assistant_id=LM_ASSITAINT_ID)


# 세션 초기화
if "is_answered" not in st.session_state:
    st.session_state["is_answered"] = False
if "quiz_data" not in st.session_state:
    st.session_state["quiz_data"] = None

st.set_page_config(page_title="QuizBot", page_icon="❓", layout="wide")
st.title("QuizBot")


# 위키백과 URL 반환 함수
def get_wikipedia_url(keyword):
    wiki_wiki = wikipediaapi.Wikipedia("MyProjectName (merlin@example.com)", "en")
    page = wiki_wiki.page(keyword)
    if page.exists():
        return page.fullurl
    else:
        st.error("위키백과에서 입력하신 키워드를 찾지 못했습니다. 다시 입력해주세요.")
        return None


# 퀴즈 생성 함수
def generate_quiz(
    docs, model_name, quiz_lang, quiz_count, quiz_type, quiz_difficulty, is_file=False
):
    with st.spinner("퀴즈 생성중..."):
        client.beta.assistants.update(assistant_id=quiz_bot.id, model=model_name)
        if is_file:
            vector_store = client.beta.vector_stores.retrieve(
                vector_store_id=QUIZBOT_VECTOR_STORE_ID
            )
            file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store.id, files=[open(file_path, "rb")]
            )

        thread = client.beta.threads.create(
            messages=[
                {
                    "role": "user",
                    "content": f"""
                    컨텍스트: {docs}
                    퀴즈 언어: {quiz_lang}
                    퀴즈 개수: {quiz_count}
                    퀴즈 유형: {quiz_type}
                    퀴즈 난이도: {quiz_difficulty}
                    """,
                }
            ]
        )
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=quiz_bot.id
        )
        messages = list(
            client.beta.threads.messages.list(thread_id=thread.id, order="desc")
        )
        
        # Check if messages list is empty
        if not messages:
            st.error("퀴즈 생성에 실패했습니다. 다시 시도해 주세요.")
            return {"questions": []}
            
        # Safely access the message content
        try:
            message_content = messages[0].content[0].text.value
            # Clean up the content
            message_content = message_content.replace("\n", "")
            print(message_content)

            # Check if the content appears to be JSON
            if "{" in message_content and "}" in message_content:
                # Try to extract just the JSON part
                json_start = message_content.find("{")
                json_end = message_content.rfind("}") + 1
                json_content = message_content[json_start:json_end]
                return json.loads(json_content)
            else:
                st.write(message_content)
                st.error("응답 형식이 올바르지 않습니다. 다시 시도해 주세요.")
                return {"questions": []}
            
        except (IndexError, AttributeError, json.JSONDecodeError) as e:
            st.error(f"퀴즈 데이터 처리 중 오류가 발생했습니다: {str(e)}")
            return {"questions": []}


def send_all_quiz_data(subjects):
    message = client.beta.threads.messages.create(
        thread_id=LM_THREAD_ID,
        role="user",
        content=f"""
        다음은 사용자가 풀어볼 퀴즈 문제의 내용입니다. 잘 기억해두세요.
        문제 키워드: {", ".join(subjects)}
        """,
    )
    # print("생성된 퀴즈 주제 전송 완료")


# 틀린 문제와 주제 전송 함수
def send_incorrect_quiz_data(questions, subjects):
    with st.spinner("풀이 결과 전송중..."):
        message = client.beta.threads.messages.create(
            thread_id=LM_THREAD_ID,
            role="user",
            content=f"""
            다음은 방금 풀어본 퀴즈에서 틀린 문제들 입니다. 잘 기억해두세요.
            틀린 문제: {"\n".join(questions)}
            틀린 문제의 키워드: {", ".join(subjects)}
            """,
        )
        # print("틀린 문제와 주제 전송 완료")


# 사이드바: 퀴즈 설정
file_name = file_path = None
docs = None
with st.sidebar:
    # 사이드바 페이지 링크
    st.page_link("pages/1-QuizBot.py", label="QuizBot")
    st.page_link("pages/2-LearningMate.py", label="LearningMate")

    with st.expander("퀴즈 설정", expanded=False):
        model_name = st.selectbox(
            "모델 선택", ("gpt-4o", "gpt-4o-mini", "o1-preview", "o1-mini"), index=0
        )
        quiz_lang = st.selectbox("퀴즈 언어", ("한국어", "영어"), index=0)
        quiz_count = st.number_input(
            "생성할 퀴즈 갯수", min_value=1, max_value=10, value=5
        )
        quiz_type = st.selectbox(
            "퀴즈 유형", ("객관식", "OX 퀴즈", "빈칸 채우기", "혼합"), index=0
        )
        quiz_difficulty = st.selectbox(
            "퀴즈 난이도", ("쉬움", "보통", "어려움"), index=1
        )

    choice = st.radio(
        "학습 자료를 선택하세요.", ("문서 파일", "위키백과", "웹 검색"), index=0
    )
    if choice == "문서 파일":
        upload_file = st.file_uploader(
            "문서 파일 업로드", type=["pdf", "txt", "docx", "md"]
        )
        if upload_file:
            file_name = upload_file.name
            file_content = upload_file.read()
            # Make sure the directory exists
            os.makedirs("./.cache/quiz_files", exist_ok=True)
            file_path = f"./.cache/quiz_files/{file_name}"
            with open(file_path, "wb") as f:
                f.write(file_content)

    elif choice == "위키백과":
        wiki_topic = st.text_input("위키백과 검색 키워드를 영어로 입력하세요.")
        if wiki_topic:
            docs = get_wikipedia_url(wiki_topic)

    elif choice == "웹 검색":
        docs = st.text_input("검색 키워드를 입력하세요.")


# 퀴즈 생성 및 데이터 처리
if not file_path and not docs:
    st.markdown(
        "#### 안녕하세요 QuizBot입니다. 퀴즈를 생성하려면 문서 파일을 업로드하거나 키워드를 입력하세요."
    )
elif file_path or docs:
    # Generate quiz button for better control
    if st.button("퀴즈 생성하기") or st.session_state["quiz_data"]:
        if not st.session_state["quiz_data"]:
            response = generate_quiz(
                docs if docs else file_path,
                model_name,
                quiz_lang,
                quiz_count,
                quiz_type,
                quiz_difficulty,
                is_file=bool(file_path),
            )
            st.session_state["quiz_data"] = response.get("questions", [])

        if st.session_state["quiz_data"]:
            wrong_questions = []
            wrong_subjects = set()
            quiz_subjects = set()
            
            # Check if quiz data has valid format
            if all(isinstance(q, dict) and "subjects" in q for q in st.session_state["quiz_data"]):
                for question in st.session_state["quiz_data"]:
                    quiz_subjects.update(question["subjects"])
                
                if quiz_subjects:
                    send_all_quiz_data(quiz_subjects)

                with st.form("questions_form"):
                    for idx, question in enumerate(st.session_state["quiz_data"]):
                        st.write(f"**질문 {idx+1}:** {question['question']}")
                        correct_answer = question["correct_answer"]

                        quiz_type = question.get("quiz_type", "객관식")  # Default to 객관식 if not specified
                        
                        if quiz_type in ("객관식", "OX 퀴즈", "OX"):
                            select_answer = st.radio(
                                label="답을 선택하세요.",
                                options=question.get("answers", []),
                                index=None,
                                key=f"radio_{idx}",
                                label_visibility="collapsed",
                            )

                            if select_answer == correct_answer:
                                st.success("정답입니다.")
                            elif select_answer:
                                st.error("오답입니다.")
                                wrong_questions.append(question["question"])
                                wrong_subjects.update(question.get("subjects", []))
                        else:
                            blank_answer = st.text_input(
                                label="답을 입력하세요.", key=f"text_{idx}"
                            )
                            if blank_answer and blank_answer.lower().strip() == correct_answer.lower().strip():
                                st.success("정답입니다.")
                            elif blank_answer:
                                st.error("오답입니다.")
                                wrong_questions.append(question["question"])
                                wrong_subjects.update(question.get("subjects", []))

                    button = st.form_submit_button("답 제출")

                if button:
                    st.session_state["is_answered"] = True
                    st.write(f"퀴즈 출처: {docs if docs else file_name}")
                    if wrong_questions:
                        send_incorrect_quiz_data(wrong_questions, list(wrong_subjects))
                    st.write("퀴즈 풀이 결과 전송됨")
            else:
                st.error("퀴즈 데이터 형식이 올바르지 않습니다. 다시 시도해 주세요.")
                st.session_state["quiz_data"] = None

# 정답 확인 및 세션 상태 초기화
if st.session_state["is_answered"]:
    if st.button("정답 확인"):
        for idx, question in enumerate(st.session_state["quiz_data"]):
            if question["question"] in wrong_questions:
                st.error(f"문제 {idx + 1}: {question['question']}")
            else:
                st.success(f"문제 {idx + 1}: {question['question']}")
            st.info(f"정답: {question['correct_answer']}")
            st.info(f"해설: {question.get('explanation', '해설 없음')}")

        if st.button("새 퀴즈 생성하기"):
            st.session_state["quiz_data"] = None
            st.session_state["is_answered"] = False
            st.experimental_rerun()