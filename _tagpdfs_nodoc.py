import streamlit as st
import os
import re
import fitz  # PyMuPDF
import pandas as pd
from pathlib import Path
import subprocess
import platform
import tempfile

st.title("Tag and Link PDFs from Word Docs")

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

# Upload Word DOC/DOCX files
uploaded_docs = st.file_uploader("Upload DOC/DOCX files", type=["doc", "docx"], accept_multiple_files=True)

# Function to convert DOC/DOCX to PDF using appropriate method per OS
def convert_doc_to_pdf(doc_path, pdf_path):
    current_os = platform.system()
    if current_os == "Windows":
        import comtypes.client
        word = comtypes.client.CreateObject('Word.Application')
        doc = word.Documents.Open(doc_path)
        doc.SaveAs(pdf_path, FileFormat=17)  # 17 = wdFormatPDF
        doc.Close()
        word.Quit()
    else:
        subprocess.run([
            "libreoffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(Path(pdf_path).parent),
            str(doc_path)
        ], check=True)

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
if uploaded_docs and tag_link_df is not None:
    for uploaded_doc in uploaded_docs:
        suffix = Path(uploaded_doc.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_doc:
            tmp_doc.write(uploaded_doc.read())
            tmp_doc_path = tmp_doc.name

        pdf_file = tmp_doc_path.replace(suffix, ".pdf")
        convert_doc_to_pdf(tmp_doc_path, pdf_file)
        tagged_pdf = tag_pdf_with_links(pdf_file, tag_link_df)

        with open(tagged_pdf, "rb") as f:
            st.download_button(
                label=f"Download Tagged PDF for {uploaded_doc.name}",
                data=f,
                file_name=Path(tagged_pdf).name,
                mime="application/pdf"
            )
