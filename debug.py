import os
import sys
import re
import base64
from typing import Tuple

from decomposed_pdf import DecomposedPDF


def decode_data_uri(data_uri: str) -> Tuple[bytes, str]:
    """
    Decode a data URI of the form: data:<mime>;base64,<payload>
    Returns (bytes, ext) where ext is derived from mime (png/jpg).
    """
    m = re.match(r"^data:([^;]+);base64,(.*)$", data_uri, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        raise ValueError("Unexpected data URI format")
    mime = m.group(1).lower().strip()
    payload_b64 = m.group(2)
    blob = base64.b64decode(payload_b64)

    if mime == "image/png":
        ext = "png"
    elif mime in ("image/jpeg", "image/jpg"):
        ext = "jpg"
    else:
        # Default to png if unknown (should not happen with the current DecomposedPDF)
        ext = "png"
    return blob, ext


def main():
    if len(sys.argv) != 2:
        print("Usage: python debug.py /path/to/file.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.isfile(pdf_path) or not pdf_path.lower().endswith(".pdf"):
        print("Error: please provide a valid path to a .pdf file.")
        sys.exit(1)

    # Prepare output folder in the current working directory
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    out_dir = os.path.join(os.getcwd(), f"{base}_debug")
    os.makedirs(out_dir, exist_ok=True)

    # Analyze the PDF (local only)
    dp = DecomposedPDF(pdf_path)
    print(f"Loaded PDF with {dp.page_count} page(s). Extracting visuals...")

    dp.extract_embedded_images()
    dp.detect_vector_regions()
    dp.render_vector_regions()

    # Write embedded images
    embedded_count = 0
    if dp.embedded_images:
        for i, (page_idx, uri) in enumerate(dp.embedded_images, start=1):
            try:
                blob, ext = decode_data_uri(uri)
                fname = f"{base}.page-{page_idx+1:03d}.img-{i:03d}.{ext}"
                fpath = os.path.join(out_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(blob)
                embedded_count += 1
            except Exception as e:
                print(f"Warning: failed to write embedded image {i} (page {page_idx+1}): {e}")
    else:
        print("No embedded images found.")

    # Write vector clips
    vector_count = 0
    if dp.vector_clips:
        for i, (page_idx, uri) in enumerate(dp.vector_clips, start=1):
            try:
                blob, ext = decode_data_uri(uri)
                fname = f"{base}.page-{page_idx+1:03d}.vector-{i:03d}.{ext}"
                fpath = os.path.join(out_dir, fname)
                with open(fpath, "wb") as f:
                    f.write(blob)
                vector_count += 1
            except Exception as e:
                print(f"Warning: failed to write vector clip {i} (page {page_idx+1}): {e}")
    else:
        print("No vector regions detected/rendered.")

    print(f"Done. Wrote {embedded_count} embedded image(s) and {vector_count} vector clip(s) to:")
    print(f"  {out_dir}")


if __name__ == "__main__":
    main()
