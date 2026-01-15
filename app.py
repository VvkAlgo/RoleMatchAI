# =========================
# app.py – Job Automation UI
# =========================

import os
import json
import base64
import pandas as pd
import streamlit as st
from datetime import datetime

# -------------------------
# GOOGLE SHEETS
# -------------------------
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# -------------------------
# GMAIL
# -------------------------
from email.message import EmailMessage
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# -------------------------
# GEMINI
# -------------------------
import google.generativeai as genai

# =========================
# STREAMLIT SETUP & HEADER
# =========================
st.set_page_config(
    page_title="RoleMatch AI",
    layout="wide",
    page_icon="🤖"
)

st.title("💼 RoleMatch AI – LinkedIn Job Automation")
st.markdown("""
**Description:**  
Automatically extract job postings, draft professional emails, and track all your applications.

**How to Use:**  
1. Upload your LinkedIn `.txt` file.  
2. Click **Analyze TXT with Gemini** to extract jobs and draft emails.  
3. Upload your resume when sending emails.  
4. Use the **Refresh Sheet** button to update your Google Sheet live.  

**Author:** Vivek Upadhyay  
**LinkedIn:** https://www.linkedin.com/in/vivek-upadhyay-6689b4184/
""")
st.markdown("---")

# CONFIG
# =========================
SHEET_NAME = "Job Tracker"
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# =========================
# UPLOAD RESUME
# =========================

st.subheader("📎 Upload Your Resume")
uploaded_resume = st.file_uploader(
    "Upload your resume (PDF only)", type=["pdf"]
)

if uploaded_resume is None:
    st.info("Please upload your resume to continue.")
    st.stop()

# =========================
# GOOGLE SHEET CONNECT
# =========================
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds_sheet = ServiceAccountCredentials.from_json_keyfile_name(
    "credentials.json", scope
)
client = gspread.authorize(creds_sheet)
sheet = client.open(SHEET_NAME).sheet1

data = pd.DataFrame(sheet.get_all_records())

st.subheader("📊 Job Tracker (Google Sheet)")
if st.button("🔄 Refresh Sheet"):
    data = pd.DataFrame(sheet.get_all_records())
    st.success("✅ Sheet refreshed")
if data.empty:
    st.info("Sheet is currently empty.")
else:
    st.dataframe(data, use_container_width=True)

# =========================
# LOAD LATEST TXT FILE
# =========================
st.subheader("📄 Upload LinkedIn TXT File")

uploaded_file = st.file_uploader(
    "Upload the LinkedIn scraped .txt file",
    type=["txt"]
)

if uploaded_file is None:
    st.info("Please upload a TXT file to continue.")
    st.stop()

gemini_input_text = uploaded_file.read().decode("utf-8", errors="ignore")
post_id = uploaded_file.name.replace(".txt", "")

st.success(f"File loaded: {uploaded_file.name}")
st.caption(f"Text length: {len(gemini_input_text)} characters")


# =========================
# GEMINI SETUP
# =========================
genai.configure(api_key="AIzaSyAnq55g2AHBg0KSSBJWUiHFYiVhSaGEgrM")
model = genai.GenerativeModel("gemini-2.5-flash")

PROMPT = """
You are a highly skilled AI assistant specialized in analyzing job postings and drafting professional job application emails.

Your input text may contain multiple, unstructured job postings scraped from LinkedIn or other sources.

Your tasks:

1. Identify ALL distinct job postings in the input text.
2. FILTER OUT any job that:
   - Does NOT provide a valid apply email
   - Is located OUTSIDE India
3. For each remaining job:
   - Extract ONLY factual information explicitly present in the text
   - Generate a professional, polite, concise email draft based on the template below
   - Ensure emails are human-like, coherent, and well-formatted

Strict JSON output schema:

{
  "jobs": [
    {
      "job_title": string,
      "company": string,
      "apply_email": string,
      "job_type": "Internship" | "Full-time" | "Contract" | "Part-time" | "Unknown",
      "location": string,
      "skills": string or null,
      "jd_summary": string,         # 1-2 sentences summarizing role, tech stack, and expectations
      "email_subject": string,      # Clear, professional subject, e.g., "Application for <Job Title> role"
      "email_body_draft": string    # Polished email, max 2 short paragraphs + closing
    }
  ]
}

Rules for `email_body_draft`:
- Base template to adapt:

"Dear Sir/Mam,

I’m applying for the Snowflake Engineer role. I have hands-on 3 years experience with Snowflake, SQL, Python, Power BI, and Matillion, along with building CI/CD pipelines on Azure. I’m a Certified Snowflake Advanced Architect and Databricks Professional Certified, with a strong focus on scalable and reliable data solutions. I’d love the opportunity to contribute to your team.
Please find my resume attached.

Best regards, 
Vivek Upadhyay
Snowflake Engineer 
vivekupadhyay_rockstar@gmail.com"

- Preserve tone and structure
- Lightly customize for each job using job title, skills, and JD summary
- Keep paragraphs short and readable
- Do NOT exaggerate, invent skills, or fabricate experience
- Ensure proper grammar and professional formatting

Additional instructions:
- Output JSON ONLY
- Do NOT include explanations, comments, or non-job content
- Ensure all extracted jobs are unique
- Validate that `apply_email` looks legitimate (contains "@" and domain)
- Include only jobs in India

TEXT TO ANALYZE:
"""

# =========================
# RUN GEMINI
# =========================
st.subheader("🤖 Analyze Jobs")

if st.button("Analyze TXT with Gemini"):
    with st.spinner("Analyzing jobs..."):
        response = model.generate_content(
            PROMPT + gemini_input_text,
            generation_config={
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        )

        gemini_output = json.loads(response.text)
        jobs = gemini_output.get("jobs", [])

        rows = []
        for idx, job in enumerate(jobs, start=1):
            rows.append(
                {
                    "job_id": idx,
                    "job_title": job.get("job_title"),
                    "company": job.get("company"),
                    "apply_email": job.get("apply_email"),
                    "jd_summary": job.get("jd_summary"),
                    "email_subject": job.get("email_subject"),
                    "email_body_draft": job.get("email_body_draft"),
                }
            )

        st.session_state["job_df"] = pd.DataFrame(rows)

# =========================
# FILTER SENT EMAILS
# =========================
if "job_df" in st.session_state:
    job_df = st.session_state["job_df"]

    if "Status" in data.columns:
        sent_emails = data.loc[
            data["Status"] == "SENT", "Contact Email"
        ].tolist()
    else:
        sent_emails = []

    job_df_filtered = job_df[
        ~job_df["apply_email"].isin(sent_emails)
    ].reset_index(drop=True)

    st.subheader("✅ Eligible Jobs")
    st.dataframe(job_df_filtered, use_container_width=True)

    if job_df_filtered.empty:
        st.warning("No new jobs available to send emails.")
        st.stop()

    # =========================
    # SELECT JOB
    # =========================
    selected_id = st.selectbox(
        "Select Job ID",
        job_df_filtered["job_id"].tolist(),
    )

    job = job_df_filtered[
        job_df_filtered["job_id"] == selected_id
    ].iloc[0]

    # =========================
    # EMAIL EDIT UI
    # =========================
    st.subheader("✉️ Email Editor")

    email_to = st.text_input("To", value=job["apply_email"])
    subject = st.text_input("Subject", value=job["email_subject"])
    body = st.text_area(
        "Email Body",
        value=job["email_body_draft"],
        height=220,
    )

    # =========================
    # GMAIL AUTH
    # =========================
    creds_gmail = None
    if os.path.exists("gmail_token.json"):
        creds_gmail = Credentials.from_authorized_user_file(
            "gmail_token.json", GMAIL_SCOPES
        )

    if not creds_gmail or not creds_gmail.valid:
        if creds_gmail and creds_gmail.expired and creds_gmail.refresh_token:
            creds_gmail.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "gmail_oauth.json", GMAIL_SCOPES
            )
            creds_gmail = flow.run_local_server(port=0)

        with open("gmail_token.json", "w") as token:
            token.write(creds_gmail.to_json())

    # =========================
    # SEND EMAIL
    # =========================
    if st.button("🚀 Send Email"):
        if email_to in sent_emails:
            st.error("This email was already sent earlier.")
            st.stop()

        gmail_service = build("gmail", "v1", credentials=creds_gmail)

        msg = EmailMessage()
        msg["To"] = email_to
        msg["From"] = "me"
        msg["Subject"] = subject
        msg.set_content(body)

        msg.add_attachment(uploaded_resume.read(),maintype="application",subtype="pdf",filename=uploaded_resume.name,)

        encoded = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        gmail_service.users().messages().send(
            userId="me", body={"raw": encoded}
        ).execute()

        # Append to sheet
        new_row = [
            str(job["job_id"]),
            job["job_title"],
            job["company"],
            email_to,
            "SENT",
            "YES",
            f"Mail sent | Subject: {subject}",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ]

        sheet.append_row(new_row)
        st.success("✅ Email sent & sheet updated")
        st.rerun()