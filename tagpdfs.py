import streamlit as st
import os
import re
import fitz  # PyMuPDF
import pandas as pd
from pathlib import Path
import tempfile
import zipfile
from datetime import datetime
import pdfplumber  # Import the table extraction library

st.title("📄 PDF Tagger + Inspection Data Extractor 4")

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

def extract_feature_information(pdf_path, feature_tag):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if text:
                    findings_match = re.search(r"3\. Inspection Findings\s*(.*?)(?=\n\w+\s*:|\n\d+\.|\Z)", text, re.DOTALL | re.IGNORECASE)
                    if findings_match:
                        findings_text = findings_match.group(1).strip()
                        # Look for the feature tag within the findings text
                        feature_info_match = re.search(rf"(?:^|\n){re.escape(feature_tag)}\s*(.*?)(?=\n\w+\s*:|\n\d+\.|\Z|\n{re.escape(feature_tag)}\s*)", findings_text, re.DOTALL | re.IGNORECASE)
                        if feature_info_match:
                            return feature_info_match.group(1).strip()
    except Exception as e:
        st.error(f"Error extracting feature information: {e}")
    return None

def extract_inspection_data(pdf_path, tags, file_date, filename):
    st.markdown(f"🔍 **Extracting inspection data from:** `{filename}`")
    extracted_data = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        # Assuming the first table is the "Inspection Site Summary"
                        if table and len(table[0]) >= 3 and table[0][0].strip() == "Feature" and table[0][1].strip() == "Last Inspection" and table[0][2].strip() == "This Inspection":
                            df = pd.DataFrame(table[1:], columns=table[0])
                            for tag in tags:
                                if tag in df['Feature'].values:
                                    row = df[df['Feature'] == tag].iloc[0]
                                    feature_info = extract_feature_information(pdf_path, tag)
                                    extracted_data.append({
                                        "Date": file_date,
                                        "Feature": row['Feature'].strip(),
                                        "Last Inspection": row['Last Inspection'].strip(),
                                        "This Inspection": row['This Inspection'].strip(),
                                        "Feature Information": feature_info,
                                        "Filename": filename,
                                        "Page Number": page_num
                                    })
                                    st.success(f"✅ Extracted data for tag: `{tag}` on page {page_num}.")
                                else:
                                    st.info(f"⚠️ Tag `{tag}` not found in the 'Inspection Site Summary' table on page {page_num}.")
    except Exception as e:
        st.error(f"❌ Error extracting data from `{filename}`: {e}")
    return extracted_data

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
all_extracted_data = []

if uploaded_pdfs and tag_link_df is not None:
    tags_to_process = tag_link_df['tag'].tolist()
    for uploaded_pdf in uploaded_pdfs:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(uploaded_pdf.read())
            tmp_pdf_path = tmp_pdf.name

        filename = uploaded_pdf.name
        file_date = extract_date_from_filename(filename)

        # Tagging
        tagged_pdf = tag_pdf_with_links(tmp_pdf_path, tag_link_df)
        tagged_pdf_name = filename.replace(".pdf", "_tagged.pdf")
        all_tagged_paths.append((tagged_pdf, tagged_pdf_name))

        # Extract Inspection Data
        extracted_info = extract_inspection_data(tagged_pdf, tags_to_process, file_date, filename)
        if extracted_info:
            all_extracted_data.extend(extracted_info)

        with open(tagged_pdf, "rb") as f:
            st.download_button(
                label=f"📥 Download Tagged PDF: {filename}",
                data=f,
                file_name=tagged_pdf_name,
                mime="application/pdf"
            )

    # --- Show Combined Data Summary ---
    if all_extracted_data:
        combined_df = pd.DataFrame(all_extracted_data)
        # Reorder columns
        column_order = ["Date", "Feature", "Last Inspection", "This Inspection", "Feature Information", "Filename", "Page Number"]
        combined_df = combined_df[column_order]
        st.markdown("## 🔍 Combined Inspection Data")
        st.dataframe(combined_df)

        # Save combined CSV
        combined_csv_path = os.path.join(tempfile.gettempdir(), "all_inspection_data_combined.csv")
        combined_df.to_csv(combined_csv_path, index=False)
        all_csv_paths.append((combined_csv_path, "all_inspection_data_combined.csv"))

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