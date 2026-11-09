import pymupdf


def extract_text_from_pdf(pdf_path):
    extracted_text = []

    with pymupdf.open(pdf_path) as document: #opens pdf files
        for page in document: #read every pages
            page_text = page.get_text("text") #extracts the text from each page

            if page_text.strip():
                extracted_text.append(page_text)#collects the extracted content.

    return "\n\n".join(extracted_text)  #combines the extracted text into one string