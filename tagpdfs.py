import streamlit as st
import os
import re
import fitz  # PyMuPDF
import pandas as pd
from pathlib import Path
import tempfile
import zipfile
from datetime import datetime

st.title("📄 PDF Tagger + Inspection Extractor")

# Upload CSV with 'tag' and 'link'
csv_file = st.file_uploader("Upload CSV with 'tag' and 'link' columns", type=["csv"])

tag_link_df = None
if csv_file:
    try:
        tag_link_df = pd.read_csv(csv_file)
        if not {'tag', 'link'}.issubset(tag_link_df.columns):
            st.error("CSV must contain 'tag' and 'link' columns.")
            tag_link_df = None
    except Exception as e:
        st.error(f"Error reading CSV: {e}")

# Upload PDF files
uploaded_pdfs = st.file_uploader("Upload PDF files to process", type=["pdf"], accept_multiple_files=True)

# --- Tagging function ---
def tag_pdf_with_links(pdf_path, tag_link_df):
    doc = fitz.open(pdf_path)
    for page in doc:
        text = page.get_text("text")
        for _, row in tag_link_df.iterrows():
            pattern = r'(?<!\w){}(?!\w)'.format(re.escape(row['tag']))
            for match in re.finditer(pattern, text):
                xrefs = page.search_for(row['tag'])
                for inst in xrefs:
                    page.insert_link({
                        "from": inst,
                        "uri": row['link'],
                        "kind": fitz.LINK_URI
                    })
    tagged_pdf_path = pdf_path.replace(".pdf", "_tagged.pdf")
    doc.save(tagged_pdf_path)
    doc.close()
    return tagged_pdf_path

# --- Extract Inspection Notes ---
def extract_inspection_notes(pdf_path, tags, file_date):
    doc = fitz.open(pdf_path)
    notes = []

    for page in doc:
        blocks = page.get_text("blocks")
        for block in blocks:
            content = block[4]
            lines = content.splitlines()
            for line in lines:
                for tag in tags:
                    if line.startswith(tag):
                        parts = re.split(r'\s{2,}|\t', line)
                        if len(parts) >= 3:
                            notes.append({
                                "Feature": parts[0].strip(),
                                "Last Inspection": parts[1].strip(),
                                "This Inspection": parts[2].strip(),
                                "Date": file_date
                            })
    doc.close()
    return notes

# --- Extract date from filename ---
def extract_date_from_filename(filename):
    match = re.search(r'\d{8}', filename)
    if match:
        try:
            return datetime.strptime(match.group(), "%Y%m%d").date()
        except:
            return ""
    return ""

# Main logic
zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
all_tagged_paths = []
all_csv_paths = []

if uploaded_pdfs and tag_link_df is not None:
    for uploaded_pdf in uploaded_pdfs:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(uploaded_pdf.read())
            tmp_pdf_path = tmp_pdf.name

        file_date = extract_date_from_filename(uploaded_pdf.name)

        tagged_pdf = tag_pdf_with_links(tmp_pdf_path, tag_link_df)
        tagged_pdf_name = uploaded_pdf.name.replace(".pdf", "_tagged.pdf")
        all_tagged_paths.append((tagged_pdf, tagged_pdf_name))

        with open(tagged_pdf, "rb") as f:
            st.download_button(
                label=f"📥 Download Tagged PDF: {uploaded_pdf.name}",
                data=f,
                file_name=tagged_pdf_name,
                mime="application/pdf"
            )

        # Extract notes
        notes = extract_inspection_notes(tagged_pdf, tag_link_df['tag'].tolist(), file_date)
        if notes:
            df_notes = pd.DataFrame(notes)
            st.write(f"### 📝 Inspection Notes: {uploaded_pdf.name}")
            st.dataframe(df_notes)

            csv_filename = uploaded_pdf.name.replace(".pdf", "_inspection_notes.csv")
            csv_path = os.path.join(tempfile.gettempdir(), csv_filename)
            df_notes.to_csv(csv_path, index=False)
            all_csv_paths.append((csv_path, csv_filename))

            with open(csv_path, "rb") as csvfile:
                st.download_button(
                    label=f"📥 Download Notes CSV: {uploaded_pdf.name}",
                    data=csvfile,
                    file_name=csv_filename,
                    mime="text/csv"
                )

    # --- Bundle tagged PDFs + CSVs into a ZIP ---
    with zipfile.ZipFile(zip_buffer.name, 'w') as zipf:
        for tagged_path, arcname in all_tagged_paths:
            zipf.write(tagged_path, arcname=arcname)
        for csv_path, csvname in all_csv_paths:
            zipf.write(csv_path, arcname=csvname)

    with open(zip_buffer.name, "rb") as f:
        st.download_button(
            label="📦 Download All Tagged PDFs + CSVs as ZIP",
            data=f,
            file_name="all_tagged_output.zip",
            mime="application/zip"
        )
