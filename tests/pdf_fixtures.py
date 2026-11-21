"""Small real PDF bytes for tests; no additional authoring dependency."""
import io

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject


def make_pdf(pages, *, encrypted=False):
    writer = PdfWriter()
    font = DictionaryObject({NameObject('/Type'): NameObject('/Font'),
                             NameObject('/Subtype'): NameObject('/Type1'),
                             NameObject('/BaseFont'): NameObject('/Helvetica')})
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        if text:
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
                DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
            lines = []
            for line in text.splitlines():
                escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
                lines.append(f'({escaped}) Tj 0 -18 Td')
            stream = DecodedStreamObject()
            stream.set_data(('BT /F1 12 Tf 50 740 Td ' + ' '.join(lines) + ' ET').encode('latin-1'))
            page[NameObject('/Contents')] = writer._add_object(stream)
    if encrypted:
        writer.encrypt('test-password')
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
