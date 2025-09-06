# decomposed_pdf.py
import io
import os
import base64
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Tuple, Dict

import fitz  # PyMuPDF
from PIL import Image


def _to_data_uri(image_bytes: bytes, ext: str) -> str:
    ext = (ext or "").lower()
    if ext in ("jpg", "jpeg"):
        mime = "image/jpeg"
    elif ext == "png":
        mime = "image/png"
    else:
        img = Image.open(io.BytesIO(image_bytes))
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        image_bytes = buf.getvalue()
        mime = "image/png"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _resize_if_needed(image_bytes: bytes, ext: str, max_dim: int) -> Tuple[bytes, str]:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        if max_dim and max(w, h) > max_dim:
            scale = max_dim / max(w, h)
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            img = img.resize(new_size, Image.LANCZOS)
            buf = io.BytesIO()
            if (ext or "").lower() in ("jpg", "jpeg"):
                img.save(buf, format="JPEG", quality=85, optimize=True)
                return buf.getvalue(), "jpeg"
            else:
                img.save(buf, format="PNG", optimize=True)
                return buf.getvalue(), "png"
    except Exception:
        pass
    return image_bytes, (ext or "").lower()


@dataclass
class DecomposedPDF:
    pdf_path: str
    # Controls for embedded images
    max_images_per_page: int = field(default_factory=lambda: int(os.environ.get("MAX_IMAGES_PER_PAGE", "2")))
    max_total_images: int = field(default_factory=lambda: int(os.environ.get("MAX_TOTAL_IMAGES", "20")))
    min_image_area: int = field(default_factory=lambda: int(os.environ.get("MIN_IMAGE_AREA", "20000")))  # w*h
    max_image_dim: int = field(default_factory=lambda: int(os.environ.get("MAX_IMAGE_DIM", "1400")))
    # Controls for vector regions
    max_vector_regions_per_page: int = field(default_factory=lambda: int(os.environ.get("MAX_VECTOR_REGIONS_PER_PAGE", "2")))
    max_vector_regions_total: int = field(default_factory=lambda: int(os.environ.get("MAX_VECTOR_REGIONS_TOTAL", "12")))
    min_vector_area_pt: float = field(default_factory=lambda: float(os.environ.get("MIN_VECTOR_AREA_PT", "5000")))
    region_pad_pt: float = field(default_factory=lambda: float(os.environ.get("REGION_PAD_PT", "6")))
    vector_render_scale: float = field(default_factory=lambda: float(os.environ.get("VECTOR_RENDER_SCALE", "2.0")))
    # Text excerpt limit
    max_text_chars: int = field(default_factory=lambda: int(os.environ.get("MAX_TEXT_CHARS", "20000")))

    # Populated
    pdf_bytes: bytes = field(init=False, default=b"")
    page_count: int = field(init=False, default=0)
    embedded_images: List[Tuple[int, str]] = field(init=False, default_factory=list)  # (page_idx, data_uri)
    vector_regions: List[Tuple[int, fitz.Rect]] = field(init=False, default_factory=list)  # (page_idx, rect)
    vector_clips: List[Tuple[int, str]] = field(init=False, default_factory=list)  # (page_idx, data_uri)

    def __post_init__(self):
        with open(self.pdf_path, "rb") as f:
            self.pdf_bytes = f.read()
        if not self.pdf_bytes:
            raise ValueError("PDF is empty or unreadable")

        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        try:
            self.page_count = len(doc)
        finally:
            doc.close()

    # ---------- Text extraction (local) ----------
    def extract_text_excerpt(self) -> str:
        """
        Extracts plain text from pages in order and returns the first max_text_chars characters.
        Includes page markers to help the model cite pages.
        """
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        try:
            chunks: List[str] = []
            total = 0
            for i in range(len(doc)):
                page = doc[i]
                txt = page.get_text("text") or ""
                if not txt.strip():
                    continue
                header = f"\n\n--- Page {i+1} ---\n"
                to_add = header + txt
                remain = self.max_text_chars - total
                if remain <= 0:
                    break
                if len(to_add) > remain:
                    chunks.append(to_add[:remain])
                    total += remain
                    break
                chunks.append(to_add)
                total += len(to_add)
            return "".join(chunks).strip()
        finally:
            doc.close()

    # ---------- Embedded raster image extraction ----------
    def extract_embedded_images(self):
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        try:
            selected: List[Tuple[int, str]] = []
            total = 0
            for page_index in range(len(doc)):
                page = doc[page_index]
                images = page.get_images(full=True)
                seen_xrefs = set()
                candidates = []
                for img in images:
                    xref = img[0]
                    if xref in seen_xrefs:
                        continue
                    seen_xrefs.add(xref)
                    try:
                        base = doc.extract_image(xref)  # {'image','ext','width','height',...}
                        w = base.get("width") or 0
                        h = base.get("height") or 0
                        area = w * h
                        if area < self.min_image_area:
                            continue
                        candidates.append((area, base))
                    except Exception:
                        continue

                candidates.sort(key=lambda t: t[0], reverse=True)
                for _, base in candidates[: self.max_images_per_page]:
                    if total >= self.max_total_images:
                        break
                    img_bytes = base["image"]
                    ext = base.get("ext", "png")
                    img_bytes, ext = _resize_if_needed(img_bytes, ext, self.max_image_dim)
                    data_uri = _to_data_uri(img_bytes, ext)
                    selected.append((page_index, data_uri))
                    total += 1
                if total >= self.max_total_images:
                    break
            self.embedded_images = selected
        finally:
            doc.close()

    # ---------- Vector region detection and rendering ----------
    @staticmethod
    def _expand_rect(r: fitz.Rect, pad: float) -> fitz.Rect:
        return fitz.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad)

    @staticmethod
    def _iou(a: fitz.Rect, b: fitz.Rect) -> float:
        inter = a & b
        if inter.is_empty:
            return 0.0
        union_area = a.get_area() + b.get_area() - inter.get_area()
        return inter.get_area() / union_area if union_area > 0 else 0.0

    def _merge_rects(self, rects: List[fitz.Rect], iou_threshold=0.15) -> List[fitz.Rect]:
        rects = rects[:]
        changed = True
        while changed:
            changed = False
            out: List[fitz.Rect] = []
            while rects:
                r = rects.pop()
                merged = False
                for i in range(len(out)):
                    if self._iou(out[i], r) >= iou_threshold or not (out[i] & r).is_empty:
                        out[i] = out[i] | r
                        merged = True
                        changed = True
                        break
                if not merged:
                    out.append(r)
            rects = out
        return rects

    def detect_vector_regions(self):
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        try:
            regions: List[Tuple[int, fitz.Rect]] = []
            total = 0
            for page_index in range(len(doc)):
                page = doc[page_index]
                draws = page.get_drawings()
                rects: List[fitz.Rect] = []
                for d in draws:
                    r = d.get("rect")
                    if not r:
                        continue
                    if r.get_area() < self.min_vector_area_pt:
                        continue
                    rects.append(self._expand_rect(r, self.region_pad_pt))
                if not rects:
                    continue
                merged = self._merge_rects(rects, iou_threshold=0.15)
                merged.sort(key=lambda R: R.get_area(), reverse=True)
                kept = 0
                for R in merged:
                    if kept >= self.max_vector_regions_per_page or total >= self.max_vector_regions_total:
                        break
                    regions.append((page_index, R))
                    kept += 1
                    total += 1
                if total >= self.max_vector_regions_total:
                    break
            self.vector_regions = regions
        finally:
            doc.close()

    def render_vector_regions(self):
        if not self.vector_regions:
            self.vector_clips = []
            return
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        try:
            out: List[Tuple[int, str]] = []
            mat = fitz.Matrix(self.vector_render_scale, self.vector_render_scale)
            for page_index, rect in self.vector_regions:
                if page_index < 0 or page_index >= len(doc):
                    continue
                page = doc[page_index]
                try:
                    pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
                    png_bytes = pix.tobytes("png")
                    data_uri = _to_data_uri(png_bytes, "png")
                    out.append((page_index, data_uri))
                except Exception:
                    continue
            self.vector_clips = out
        finally:
            doc.close()

    # ---------- Build Chat Completions multimodal user parts ----------
    def build_user_parts(self, instruction: str, include_text_excerpt: bool = True) -> List[Dict]:
        parts: List[Dict] = [{"type": "text", "text": instruction}]
        if include_text_excerpt:
            excerpt = self.extract_text_excerpt()
            if excerpt:
                parts.append({"type": "text", "text": "Extracted text excerpt (may be truncated):\n" + excerpt})

        # Group visuals by page so the model can cite page numbers
        by_page: Dict[int, Dict[str, List[str]]] = defaultdict(lambda: {"images": [], "vectors": []})
        for p, uri in self.embedded_images:
            by_page[p]["images"].append(uri)
        for p, uri in self.vector_clips:
            by_page[p]["vectors"].append(uri)

        if by_page:
            parts.append({"type": "text", "text": "Extracted visuals by page:"})
            for page_index in sorted(by_page.keys()):
                bucket = by_page[page_index]
                label_bits = []
                if bucket["images"]:
                    label_bits.append(f"{len(bucket['images'])} embedded image(s)")
                if bucket["vectors"]:
                    label_bits.append(f"{len(bucket['vectors'])} vector clip(s)")
                parts.append({"type": "text", "text": f"Page {page_index + 1} ({', '.join(label_bits)}):"})
                for uri in bucket["images"]:
                    parts.append({"type": "image_url", "image_url": {"url": uri, "detail": "auto"}})
                for uri in bucket["vectors"]:
                    parts.append({"type": "image_url", "image_url": {"url": uri, "detail": "auto"}})

        return parts
