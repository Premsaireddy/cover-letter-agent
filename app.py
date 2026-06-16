import re
from io import BytesIO

import streamlit as st
from dotenv import load_dotenv
from docx import Document
from openai import OpenAI
from pypdf import PdfReader

load_dotenv()
client = OpenAI()

st.set_page_config(page_title="AI Cover Letter Agent", page_icon="📝")

st.title("AI Cover Letter Agent")
st.write("Upload your CV, paste a job description, and the agent will draft, critique, and improve your cover letter.")

uploaded_cv = st.file_uploader("Upload your CV", type=["pdf", "docx"])
job_description = st.text_area("Paste the job description", height=280)


# --- BACKEND LOGIC FUNCTIONS ---

def extract_pdf_text(pdf_file):
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"
    return text


def extract_docx_text(docx_file):
    doc = Document(docx_file)
    text = ""
    for paragraph in doc.paragraphs:
        if paragraph.text.strip():
            text += paragraph.text + "\n"
    return text


def ask_ai(prompt):
    response = client.chat.completions.create(
        model="o3-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content


def write_first_draft(cv_text, job_description):
    prompt = f"""
You are an expert cover letter writer.
Write a tailored cover letter using the CV and job description below.

Rules:
- Do not invent experience. Use only information from the CV.
- Match the candidate's skills explicitly to the job requirements.
- Keep it professional and concise — between 250 and 400 words.
- Make it suitable for graduate, internship, or entry-level roles.
- Start with a specific hook referencing the company or role — never open with "I am writing to apply for..."
- Output only the cover letter text. No preamble, no labels, no commentary.

CV:
{cv_text}

Job Description:
{job_description}
"""
    return ask_ai(prompt)


def critique_cover_letter(cv_text, job_description, cover_letter):
    prompt = f"""
You are a strict recruiter reviewing a cover letter.
Score it out of 10 by averaging these six criteria (each worth up to 1-2 points):
1. Relevance to the job description
2. Evidence drawn from the CV (concrete, not vague)
3. Professional tone
4. Specificity (names the company/role, references exact requirements)
5. No invented claims (everything traceable to the CV)
6. Clear structure (strong opening, body, closing)

YOU MUST respond in EXACTLY this format — no preamble, no variation whatsoever:
Score: X/10

Feedback:
- point 1
- point 2
- point 3

CV:
{cv_text}

Job Description:
{job_description}

Cover Letter:
{cover_letter}
"""
    return ask_ai(prompt)


def improve_cover_letter(cv_text, job_description, cover_letter, critique, score, target_score):
    prompt = f"""
You are an expert cover letter writer.
The previous cover letter scored {score}/10. The target is {target_score}/10.
Improve it by carefully addressing every point in the recruiter's feedback below.

Rules:
- Do not invent anything not present in the CV or job description.
- Keep it between 250 and 400 words.
- Be more specific: reference the company name, exact role title, and concrete requirements from the job description.
- Fix every issue raised in the feedback — do not ignore any point.
- Keep the strong parts of the original letter intact.
- Output only the improved cover letter text. No preamble, no labels, no commentary.

CV:
{cv_text}

Job Description:
{job_description}

Original Cover Letter:
{cover_letter}

Recruiter Feedback:
{critique}
"""
    return ask_ai(prompt)


def extract_score(critique_text):
    match = re.search(r"Score:\s*(\d+(?:\.\d+)?)\s*/\s*10", critique_text, re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 0


def create_docx(text):
    doc = Document()
    doc.add_heading("Cover Letter", level=1)
    for paragraph in text.split("\n"):
        if paragraph.strip():
            doc.add_paragraph(paragraph.strip())
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


# --- AGENT EXECUTION TRIGGER ---

if st.button("Generate Cover Letter"):
    if uploaded_cv is None:
        st.error("Please upload your CV as PDF or DOCX.")
        st.stop()

    if not job_description.strip():
        st.error("Please paste the job description.")
        st.stop()

    with st.spinner("Reading your CV..."):
        if uploaded_cv.name.lower().endswith(".pdf"):
            cv_text = extract_pdf_text(uploaded_cv)
        elif uploaded_cv.name.lower().endswith(".docx"):
            cv_text = extract_docx_text(uploaded_cv)
        else:
            st.error("Unsupported file type.")
            st.stop()

    if not cv_text.strip():
        st.error("Could not read your CV. Please check the file.")
        st.stop()

    target_score = 8
    max_attempts = 3
    attempts_log = []

    # Dynamic status container to show the agent thinking
    status_box = st.empty()

    status_box.info("🤖 Agent is writing the first draft...")
    current_letter = write_first_draft(cv_text, job_description)

    for attempt in range(1, max_attempts + 1):
        status_box.info(f"🕵️‍♂️ Recruiter Agent is reviewing attempt {attempt}...")
        critique = critique_cover_letter(
            cv_text=cv_text,
            job_description=job_description,
            cover_letter=current_letter
        )

        score = extract_score(critique)
        attempts_log.append({
            "attempt": attempt,
            "score": score,
            "critique": critique
        })

        if score >= target_score:
            status_box.success(f"🎉 Success! Target score reached ({score}/10) on attempt {attempt}.")
            break

        if attempt < max_attempts:
            status_box.warning(f"⚠️ Score was {score}/10. Agent is executing a revision loop...")
            current_letter = improve_cover_letter(
                cv_text=cv_text,
                job_description=job_description,
                cover_letter=current_letter,
                critique=critique,
                score=score,
                target_score=target_score
            )
        else:
            status_box.error(f"🛑 Reached maximum loops ({max_attempts}). Outputting best version.")

    # Save results to session state so they survive the Streamlit rerun cycle
    st.session_state['final_letter'] = current_letter
    st.session_state['attempts_log'] = attempts_log


# --- RENDER RESULTS (Outside the button condition block) ---

if 'final_letter' in st.session_state:
    st.subheader("Agent Iteration Log")
    for item in st.session_state['attempts_log']:
        with st.expander(f"Attempt {item['attempt']} — Score: {item['score']}/10"):
            st.write(item["critique"])

    st.subheader("Final Cover Letter")
    st.write(st.session_state['final_letter'])

    docx_file = create_docx(st.session_state['final_letter'])

    st.download_button(
        label="Download Cover Letter as DOCX",
        data=docx_file,
        file_name="cover_letter.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )