import streamlit as st
import os
import re
import fitz  # PyMuPDF
import pandas as pd
from pathlib import Path
import tempfile
import zipfile

st.title("Tag and Link Existing PDFs")

# Load CSV containing 'tag' and 'link'
csv_file = st.file_uploader("Upload CSV file with 'tag' and 'link' columns", type=["csv"])

tag_link_df = None
if csv_file:
    try:
        tag_link_df = pd.read_csv(csv_file)
        if not {'tag', 'link'}.issubset(tag_link_df.columns):
            st.error("CSV must contain 'tag' and 'link' columns.")
            tag_link_df = None
    except Exception as e:
        st.error(f"Failed to read CSV: {e}")

# Upload PDF files
uploaded_pdfs = st.file_uploader("Upload PDFs to tag", type=["pdf"], accept_multiple_files=True)

# Function to tag PDFs with links based on tags
def tag_pdf_with_links(pdf_path, tag_link_df):
    doc = fitz.open(pdf_path)
    for page in doc:
        text = page.get_text("text")
        for _, row in tag_link_df.iterrows():
            pattern = r'(?<!\\w){}(?!\\w)'.format(re.escape(row['tag']))
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

# Main processing
zip_buffer = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
all_tagged_paths = []

if uploaded_pdfs and tag_link_df is not None:
    for uploaded_pdf in uploaded_pdfs:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
            tmp_pdf.write(uploaded_pdf.read())
            tmp_pdf_path = tmp_pdf.name

        tagged_pdf = tag_pdf_with_links(tmp_pdf_path, tag_link_df)
        all_tagged_paths.append((tagged_pdf, uploaded_pdf.name.replace(".pdf", "_tagged.pdf")))

        with open(tagged_pdf, "rb") as f:
            st.download_button(
                label=f"Download Tagged PDF for {uploaded_pdf.name}",
                data=f,
                file_name=Path(tagged_pdf).name,
                mime="application/pdf"
            )

    # Create a ZIP file
    with zipfile.ZipFile(zip_buffer.name, 'w') as zipf:
        for tagged_path, arcname in all_tagged_paths:
            zipf.write(tagged_path, arcname=arcname)

    with open(zip_buffer.name, "rb") as f:
        st.download_button(
            label="Download All Tagged PDFs as ZIP",
            data=f,
            file_name="tagged_pdfs.zip",
            mime="application/zip"
        )
