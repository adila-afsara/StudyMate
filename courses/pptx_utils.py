
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE


def extract_text_from_pptx(file_path):
    """
    Extract text from PowerPoint (.pptx) slides.

    Supports:
    - Slide text boxes
    - Slide titles
    - Text placeholders
    - Tables
    - Grouped shapes

    Returns extracted text as a string.
    """

    presentation = Presentation(file_path)
    extracted_slides = []

    def extract_shape_text(shape):
        parts = []

        # Handle grouped shapes recursively
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            for child_shape in shape.shapes:
                parts.extend(extract_shape_text(child_shape))
            return parts

        # Extract text from ordinary text shapes
        if shape.has_text_frame:
            text = shape.text.strip()
            if text:
                parts.append(text)

        # Extract table contents
        if shape.has_table:
            for row in shape.table.rows:
                cells = [
                    cell.text.strip()
                    for cell in row.cells
                ]
                if any(cells):
                    parts.append(" | ".join(cells))

        return parts

    # Process each slide in order
    for slide_number, slide in enumerate(
        presentation.slides, start=1
    ):
        slide_parts = []

        for shape in slide.shapes:
            slide_parts.extend(extract_shape_text(shape))

        if slide_parts:
            slide_text = "\n".join(slide_parts)

            extracted_slides.append(
                f"Slide {slide_number}:\n{slide_text}"
            )

    return "\n\n".join(extracted_slides)

