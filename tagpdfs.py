import streamlit as st
import os
import re
import fitz  # PyMuPDF
import pandas as pd
from pathlib import Path
import tempfile
import zipfile
from datetime import datetime

st.title("📄 PDF Tagger + Inspection Notes Extractor")

# --- Upload CSV ---
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

# --- Upload PDFs ---
uploaded_pdfs = st.file_uploader("Upload PDF files to process", type=["pdf"], accept_multiple_files=True)

# --- Helper Functions ---
def tag_pdf_with_links(pdf_path, tag_link_df):
    doc = fitz.open(pdf_path)
    for page in doc:
        text = page.get_text("text")
        for _, row in tag_link_df.iterrows():
            if row['tag'] not in text:
                continue
            matches = page.search_for(row['tag'])
            for inst in matches:
                page.insert_link({
                    "from": inst,
                    "uri": row['link'],
                    "kind": fitz.LINK_URI
                })
    tagged_pdf_path = pdf_path.replace(".pdf", "_tagged.pdf")
    doc.save(tagged_pdf_path)
    doc.close()
    return tagged_pdf_path

def extract_inspection_notes(pdf_path, tags, file_date):
    doc = fitz.open(pdf_path)
    notes = []
    for page in doc:
        blocks = page.get_text("blocks")
        for block in blocks:
            content = block[4]
            for line in content.splitlines():
                for tag in tags:
                    if line.strip().startswith(tag):
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

def extract_date_from_filename(filename):
    match = re.search(r'\d{8}', filename)
    if match:
        try:
            return datetime.strptime(match.group(), "%Y%m%d").date()
        except:
            return ""
    return ""

# --- Main Logic ---
zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
all_tagged_paths = []
all_csv_paths = []
all_combined_notes = []

if uploaded_pdfs and tag_link_df is not None:
    for uploaded_pdf in uploaded_pdfs:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(uploaded_pdf.read())
            tmp_pdf_path = tmp_pdf.name

        file_date = extract_date_from_filename(uploaded_pdf.name)

        # Tagging
        tagged_pdf = tag_pdf_with_links(tmp_pdf_path, tag_link_df)
        tagged_pdf_name = uploaded_pdf.name.replace(".pdf", "_tagged.pdf")
        all_tagged_paths.append((tagged_pdf, tagged_pdf_name))

        # Notes Extraction
        notes = extract_inspection_notes(tagged_pdf, tag_link_df['tag'].tolist(), file_date)
        if notes:
            df_notes = pd.DataFrame(notes)
            all_combined_notes.append(df_notes)

            csv_filename = uploaded_pdf.name.replace(".pdf", "_inspection_notes.csv")
            csv_path = os.path.join(tempfile.gettempdir(), csv_filename)
            df_notes.to_csv(csv_path, index=False)
            all_csv_paths.append((csv_path, csv_filename))

            with open(tagged_pdf, "rb") as f:
                st.download_button(
                    label=f"📥 Download Tagged PDF: {uploaded_pdf.name}",
                    data=f,
                    file_name=tagged_pdf_name,
                    mime="application/pdf"
                )

            with open(csv_path, "rb") as csvfile:
                st.download_button(
                    label=f"📥 Download Notes CSV: {uploaded_pdf.name}",
                    data=csvfile,
                    file_name=csv_filename,
                    mime="text/csv"
                )

    # --- Show Combined Notes Summary ---
    if all_combined_notes:
        combined_df = pd.concat(all_combined_notes, ignore_index=True)
        st.markdown("## 🔍 Combined Inspection Summary")
        st.dataframe(combined_df)

        # Save combined CSV
        combined_csv_path = os.path.join(tempfile.gettempdir(), "all_inspection_notes_combined.csv")
        combined_df.to_csv(combined_csv_path, index=False)
        all_csv_paths.append((combined_csv_path, "all_inspection_notes_combined.csv"))

    # --- Final ZIP ---
    with zipfile.ZipFile(zip_buffer.name, 'w') as zipf:
        for tagged_path, arcname in all_tagged_paths:
            zipf.write(tagged_path, arcname=arcname)
        for csv_path, arcname in all_csv_paths:
            zipf.write(csv_path, arcname=arcname)

    with open(zip_buffer.name, "rb") as f:
        st.download_button(
            label="📦 Download All Tagged PDFs + CSVs as ZIP",
            data=f,
            file_name="tagged_pdfs_and_csvs.zip",
            mime="application/zip"
        )
