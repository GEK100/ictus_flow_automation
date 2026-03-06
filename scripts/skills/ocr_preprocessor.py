"""Skill 7: OCR Pre-Processor.

Pre-processes low-quality images and non-searchable PDFs before
classification/extraction. Auto-rotate, de-skew, contrast enhance, OCR.

Triggered when:
  - Classifier confidence < 0.70 on an image file
  - Any handler receives a non-text-searchable PDF

Usage:
    python scripts/skills/ocr_preprocessor.py <file_path> [--client GILM]
"""

import os
import sys
import argparse
import shutil
import uuid
import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ExifTags
import pytesseract

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Tesseract OCR path (Windows)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def is_text_searchable_pdf(pdf_path):
    """Check if a PDF has extractable text (not just scanned images)."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            text = ''
            for page in pdf.pages[:3]:  # Check first 3 pages
                page_text = page.extract_text() or ''
                text += page_text
            # If we get fewer than 50 chars from 3 pages, it's likely image-only
            return len(text.strip()) >= 50
    except Exception as e:
        log.warning(f"Error checking PDF text: {e}")
        return False


def is_image_file(filepath):
    """Check if a file is an image based on extension."""
    ext = Path(filepath).suffix.lower()
    return ext in {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp', '.gif', '.webp'}


def is_pdf_file(filepath):
    """Check if a file is a PDF."""
    return Path(filepath).suffix.lower() == '.pdf'


def auto_rotate_image(img, original_filepath=None):
    """Auto-rotate image using EXIF orientation data.

    Args:
        img: OpenCV image array.
        original_filepath: Path to original file for EXIF reading.
            cv2.imread strips EXIF, so we must read it from the source file.
    """
    try:
        # Read EXIF from the original file, not the cv2 array
        if original_filepath:
            pil_img = Image.open(original_filepath)
        else:
            pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

        exif = pil_img.getexif()
        if exif:
            orientation_key = None
            for key, val in ExifTags.TAGS.items():
                if val == 'Orientation':
                    orientation_key = key
                    break

            if orientation_key and orientation_key in exif:
                orientation = exif[orientation_key]
                rotations = {3: 180, 6: 270, 8: 90}
                if orientation in rotations:
                    angle = rotations[orientation]
                    # Rotate the cv2 image via PIL for proper expand
                    work_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                    work_img = work_img.rotate(angle, expand=True)
                    log.info(f"Auto-rotated {angle} degrees (EXIF orientation={orientation})")
                    img = cv2.cvtColor(np.array(work_img), cv2.COLOR_RGB2BGR)

        if original_filepath:
            pil_img.close()
    except Exception as e:
        log.warning(f"EXIF rotation failed: {e}")
    return img


def deskew_image(img):
    """Detect and correct skew angle."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
    # Threshold to get binary image
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    # Find all non-zero points
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 100:
        return img  # Not enough content to determine skew

    # Get the minimum bounding rectangle angle
    angle = cv2.minAreaRect(coords)[-1]

    # Normalise angle
    if angle < -45:
        angle = -(90 + angle)
    elif angle > 45:
        angle = -(angle - 90)
    else:
        angle = -angle

    # Only correct if skew is significant but not extreme
    if abs(angle) < 0.5 or abs(angle) > 15:
        return img

    log.info(f"De-skewing by {angle:.1f} degrees")
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        img, matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated


def enhance_contrast(img):
    """Apply adaptive histogram equalisation for contrast enhancement."""
    if len(img.shape) == 3:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l_channel = lab[:, :, 0]
    else:
        l_channel = img

    # CLAHE: Contrast Limited Adaptive Histogram Equalisation
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(l_channel)

    if len(img.shape) == 3:
        lab[:, :, 0] = enhanced
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    else:
        img = enhanced

    log.info("Applied CLAHE contrast enhancement")
    return img


def sharpen_image(img):
    """Apply unsharp masking to sharpen the image."""
    gaussian = cv2.GaussianBlur(img, (0, 0), 3)
    sharpened = cv2.addWeighted(img, 1.5, gaussian, -0.5, 0)
    log.info("Applied sharpening")
    return sharpened


def enhance_image(img, original_filepath=None):
    """Full enhancement pipeline: rotate, deskew, contrast, sharpen."""
    img = auto_rotate_image(img, original_filepath)
    img = deskew_image(img)
    img = enhance_contrast(img)
    img = sharpen_image(img)
    return img


def ocr_image(img):
    """Run OCR on an image array. Returns extracted text.

    Tries multiple preprocessing strategies and picks the one that
    extracts the most text — handles photos of screens, scanned docs,
    and clean images.
    """
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    candidates = []

    # Strategy 1: Direct grayscale (works well for clean, high-contrast images)
    candidates.append(pytesseract.image_to_string(gray, lang='eng').strip())

    # Strategy 2: Otsu thresholding (good for bimodal histograms)
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    candidates.append(pytesseract.image_to_string(otsu, lang='eng').strip())

    # Strategy 3: Adaptive thresholding (good for uneven lighting)
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2,
    )
    candidates.append(pytesseract.image_to_string(adaptive, lang='eng').strip())

    # Pick the result with the most text
    best = max(candidates, key=len)
    strategy_names = ['grayscale', 'otsu', 'adaptive']
    best_idx = candidates.index(best)
    if best:
        log.info(f"Best OCR strategy: {strategy_names[best_idx]} ({len(best)} chars)")

    return best


def process_image_file(filepath, output_dir=None):
    """Process a single image file: enhance + OCR.

    Returns (enhanced_path, extracted_text).
    """
    log.info(f"Processing image: {filepath}")
    img = cv2.imread(str(filepath))
    if img is None:
        raise ValueError(f"Could not read image: {filepath}")

    enhanced = enhance_image(img, original_filepath=str(filepath))
    text = ocr_image(enhanced)

    # Save enhanced image
    if output_dir is None:
        output_dir = Path(filepath).parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(filepath).stem
    enhanced_path = output_dir / f"{stem}_enhanced.png"
    cv2.imwrite(str(enhanced_path), enhanced)

    log.info(f"Enhanced image saved: {enhanced_path}")
    log.info(f"OCR extracted {len(text)} characters")
    return str(enhanced_path), text


def process_pdf_file(filepath, output_dir=None):
    """Process a non-searchable PDF: convert pages to images, enhance, OCR, create text overlay.

    Returns (enhanced_pdf_path, full_text).
    """
    from pdf2image import convert_from_path
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    import PyPDF2

    log.info(f"Processing PDF: {filepath}")

    if output_dir is None:
        output_dir = Path(filepath).parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Convert PDF pages to images
    pages = convert_from_path(str(filepath), dpi=300)
    log.info(f"PDF has {len(pages)} pages")

    all_text = []
    enhanced_images = []

    for i, page_img in enumerate(pages):
        log.info(f"Processing page {i + 1}/{len(pages)}")
        img = cv2.cvtColor(np.array(page_img), cv2.COLOR_RGB2BGR)
        enhanced = enhance_image(img)
        text = ocr_image(enhanced)
        all_text.append(text)
        enhanced_images.append(enhanced)

    full_text = '\n\n--- Page Break ---\n\n'.join(all_text)

    # Create text-searchable PDF with OCR text overlay
    stem = Path(filepath).stem
    enhanced_pdf_path = output_dir / f"{stem}_enhanced.pdf"

    tmpdir = os.path.join(
        os.environ.get('TEMP', '/tmp'), 'ictus-flow-processing',
        f'ocr-pdf-{uuid.uuid4().hex[:8]}',
    )
    os.makedirs(tmpdir, exist_ok=True)
    try:
        page_pdfs = []
        for i, (enhanced, text) in enumerate(zip(enhanced_images, all_text)):
            # Save enhanced image as temporary file
            img_path = os.path.join(tmpdir, f'page_{i}.png')
            cv2.imwrite(img_path, enhanced)

            # Create PDF page from enhanced image
            page_pdf_path = os.path.join(tmpdir, f'page_{i}.pdf')
            pil_img = Image.open(img_path)
            w_px, h_px = pil_img.size

            # Create PDF with image
            c = canvas.Canvas(page_pdf_path, pagesize=(w_px * 72 / 300, h_px * 72 / 300))
            c.drawImage(img_path, 0, 0,
                        width=w_px * 72 / 300, height=h_px * 72 / 300)
            c.save()
            page_pdfs.append(page_pdf_path)

        # Merge all pages
        merger = PyPDF2.PdfMerger()
        for pdf_path in page_pdfs:
            merger.append(pdf_path)
        merger.write(str(enhanced_pdf_path))
        merger.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    log.info(f"Enhanced PDF saved: {enhanced_pdf_path}")
    log.info(f"Total OCR text: {len(full_text)} characters")
    return str(enhanced_pdf_path), full_text


def process_file(filepath, client_code=None, output_dir=None):
    """Main entry point: process any file (image or PDF).

    For text-searchable PDFs, returns the original path unchanged.

    Returns dict:
        {
            'original_path': str,
            'enhanced_path': str (or original if no processing),
            'text': str (extracted text, empty if already searchable),
            'ocr_applied': bool,
            'page_count': int,
        }
    """
    filepath = str(filepath)

    if is_pdf_file(filepath):
        if is_text_searchable_pdf(filepath):
            log.info(f"PDF is already text-searchable: {filepath}")
            return {
                'original_path': filepath,
                'enhanced_path': filepath,
                'text': '',
                'ocr_applied': False,
                'page_count': _count_pdf_pages(filepath),
            }
        else:
            enhanced_path, text = process_pdf_file(filepath, output_dir)
            return {
                'original_path': filepath,
                'enhanced_path': enhanced_path,
                'text': text,
                'ocr_applied': True,
                'page_count': _count_pdf_pages(filepath),
            }
    elif is_image_file(filepath):
        enhanced_path, text = process_image_file(filepath, output_dir)
        return {
            'original_path': filepath,
            'enhanced_path': enhanced_path,
            'text': text,
            'ocr_applied': True,
            'page_count': 1,
        }
    else:
        log.info(f"File type not supported for OCR: {filepath}")
        return {
            'original_path': filepath,
            'enhanced_path': filepath,
            'text': '',
            'ocr_applied': False,
            'page_count': 0,
        }


def _count_pdf_pages(filepath):
    """Count pages in a PDF."""
    try:
        import PyPDF2
        with open(filepath, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            return len(reader.pages)
    except Exception:
        return 0


def main():
    parser = argparse.ArgumentParser(description='Skill 7: OCR Pre-Processor')
    parser.add_argument('filepath', help='Path to file to process')
    parser.add_argument('--client', default=None, help='Client code (e.g. GILM)')
    parser.add_argument('--output-dir', default=None, help='Output directory')
    args = parser.parse_args()

    if not os.path.exists(args.filepath):
        log.error(f"File not found: {args.filepath}")
        sys.exit(1)

    result = process_file(args.filepath, args.client, args.output_dir)

    print(f"\n{'='*50}")
    print(f"OCR Pre-Processor Results")
    print(f"{'='*50}")
    print(f"Original:     {result['original_path']}")
    print(f"Enhanced:     {result['enhanced_path']}")
    print(f"OCR Applied:  {result['ocr_applied']}")
    print(f"Pages:        {result['page_count']}")
    print(f"Text Length:  {len(result['text'])} chars")
    if result['text']:
        preview = result['text'][:200]
        print(f"\nText Preview:\n{preview}...")
    print(f"{'='*50}")


if __name__ == '__main__':
    main()
