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

st.title("📄 PDF Tagger + Inspection Notes & Tables Extractor 3")

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
    st.markdown(f"🔍 **Extracting inspection notes from:** `{Path(pdf_path).name}`")
    notes = []

    try:
        doc = fitz.open(pdf_path)
        tag_hits = {tag: 0 for tag in tags}

        for page_num, page in enumerate(doc, start=1):
            blocks = page.get_text("blocks")
            for block in blocks:
                content = block[4]
                # st.warning(content)  # Debugging line

                for line in content.splitlines():
                    for tag in tags:
                        if re.match(rf'^\s*{re.escape(tag)}\b', line, re.IGNORECASE):
                            st.info(f"✅ Match found for tag: `{tag}` in line: `{line}`")
                            parts = re.split(r'\s{2,}|\t', line)
                            if len(parts) >= 3:
                                notes.append({
                                    "Feature": parts[0].strip(),
                                    "Last Inspection": parts[1].strip(),
                                    "This Inspection": parts[2].strip(),
                                    "Date": file_date
                                })
                                tag_hits[tag] += 1

        doc.close()

        total_found = sum(tag_hits.values())
        if total_found == 0:
            st.warning(f"⚠️ No inspection notes found in `{Path(pdf_path).name}`.")
        else:
            st.success(f"✅ Found {total_found} inspection entries.")
            for tag, count in tag_hits.items():
                if count > 0:
                    st.write(f"- **{tag}**: {count} match{'es' if count > 1 else ''}")

    except Exception as e:
        st.error(f"❌ Error while extracting notes from `{Path(pdf_path).name}`: {e}")

    return notes

def extract_tables_from_pdf(pdf_path):
    st.markdown(f"📊 **Extracting tables from:** `{Path(pdf_path).name}`")
    all_tables = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                if tables:
                    st.info(f"✅ Found {len(tables)} table(s) on page {i+1}.")
                    for j, table in enumerate(tables):
                        df = pd.DataFrame(table[1:], columns=table[0]) if table else pd.DataFrame()
                        if not df.empty:
                            all_tables.append(df)
                            st.dataframe(df) # Display each table in Streamlit
                else:
                    st.info(f"⚠️ No tables found on page {i+1}.")
    except Exception as e:
        st.error(f"❌ Error while extracting tables from `{Path(pdf_path).name}`: {e}")
    return all_tables

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
all_extracted_tables = {} # Dictionary to store DataFrames per file

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

            with open(csv_path, "rb") as csvfile:
                st.download_button(
                    label=f"📥 Download Notes CSV: {uploaded_pdf.name}",
                    data=csvfile,
                    file_name=csv_filename,
                    mime="text/csv"
                )

        # Table Extraction
        extracted_tables = extract_tables_from_pdf(tagged_pdf)
        if extracted_tables:
            all_extracted_tables[uploaded_pdf.name] = extracted_tables
            for i, df_table in enumerate(extracted_tables):
                table_csv_filename = uploaded_pdf.name.replace(".pdf", f"_table_{i+1}.csv")
                table_csv_path = os.path.join(tempfile.gettempdir(), table_csv_filename)
                df_table.to_csv(table_csv_path, index=False)
                all_csv_paths.append((table_csv_path, table_csv_filename))
                with open(table_csv_path, "rb") as table_csv_file:
                    st.download_button(
                        label=f"📥 Download Table {i+1} CSV: {uploaded_pdf.name}",
                        data=table_csv_file,
                        file_name=table_csv_filename,
                        mime="text/csv"
                    )

        with open(tagged_pdf, "rb") as f:
            st.download_button(
                label=f"📥 Download Tagged PDF: {uploaded_pdf.name}",
                data=f,
                file_name=tagged_pdf_name,
                mime="application/pdf"
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