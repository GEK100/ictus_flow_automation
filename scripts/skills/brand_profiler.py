"""Skill 1: Brand Profiler.

Scans client documents from 05-BRAND-ASSETS to extract visual identity:
colours, fonts, layout, date format, reference numbering.

Usage:
    python scripts/skills/brand_profiler.py <client_code>
"""

import os
import sys
import json
import argparse
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from collections import Counter

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.utils import claude_client, drive_client
from scripts.utils.prompt_builder import load_base_prompt, load_client_config
from scripts.utils.client_guard import validate_client_operation


BRAND_EXTRACTION_PROMPT = None


def get_extraction_prompt():
    global BRAND_EXTRACTION_PROMPT
    if BRAND_EXTRACTION_PROMPT is None:
        BRAND_EXTRACTION_PROMPT = load_base_prompt('brand-profiler.txt')
    return BRAND_EXTRACTION_PROMPT


def extract_brand_from_document(filepath, client_code):
    """Send a single document to Opus for brand extraction.

    Returns dict with extracted brand fields.
    """
    system_prompt = get_extraction_prompt()

    # For images, send as vision input
    images = None
    ext = Path(filepath).suffix.lower()
    if ext in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.tiff', '.tif', '.bmp'}:
        images = [claude_client.encode_image_file(filepath)]
        prompt = f"Analyse this document image and extract all brand elements."
    elif ext == '.pdf':
        # Convert first page to image for visual analysis
        try:
            images = [claude_client.encode_pdf_page_as_image(filepath, 0)]
            prompt = f"Analyse this document page and extract all brand elements."
        except Exception as e:
            log.warning(f"Could not convert PDF to image: {e}")
            # Fall back to text extraction
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                text = ''
                for page in pdf.pages[:5]:
                    text += (page.extract_text() or '') + '\n'
            prompt = f"Analyse this document text and extract all brand elements:\n\n{text[:4000]}"
    elif ext == '.docx':
        from docx import Document
        doc = Document(filepath)
        text = '\n'.join(p.text for p in doc.paragraphs)
        prompt = f"Analyse this document text and extract all brand elements:\n\n{text[:4000]}"
    else:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read(4000)
        prompt = f"Analyse this document and extract all brand elements:\n\n{text}"

    return claude_client.send_message_json(
        prompt=prompt,
        system_prompt=system_prompt,
        model_tier='MODEL_COMPLEX',
        max_tokens=2000,
        client_code=client_code,
        workflow='brand-profiler',
        images=images,
    )


def consensus_field(values):
    """Apply majority-wins consensus logic. Returns (winner, confidence)."""
    if not values:
        return None, 0.0
    filtered = [v for v in values if v and v != 'unknown']
    if not filtered:
        return None, 0.0
    counter = Counter(filtered)
    winner, count = counter.most_common(1)[0]
    confidence = count / len(filtered)
    return winner, confidence


def aggregate_profiles(extractions):
    """Aggregate multiple document extractions into a single brand profile.

    Uses majority-wins consensus for each field.
    """
    colours_primary = []
    colours_secondary = []
    colours_accent = []
    fonts_primary = []
    fonts_secondary = []
    date_formats = []
    ref_patterns = []
    logo_positions = []

    for ext in extractions:
        colours = ext.get('colours', {})
        if isinstance(colours, dict):
            if colours.get('primary'):
                colours_primary.append(colours['primary'])
            if colours.get('secondary'):
                colours_secondary.append(colours['secondary'])
            if colours.get('accent'):
                colours_accent.append(colours['accent'])

        fonts = ext.get('fonts', {})
        if isinstance(fonts, dict):
            if fonts.get('primary'):
                fonts_primary.append(fonts['primary'])
            if fonts.get('secondary'):
                fonts_secondary.append(fonts['secondary'])

        layout = ext.get('layout', {})
        if isinstance(layout, dict):
            if layout.get('date_format'):
                date_formats.append(layout['date_format'])
            if layout.get('reference_pattern'):
                ref_patterns.append(layout['reference_pattern'])
            if layout.get('logo_position'):
                logo_positions.append(layout['logo_position'])

    # Build consensus profile
    gaps = []

    def resolve(values, field_name):
        winner, conf = consensus_field(values)
        if winner is None or conf < 0.4:
            gaps.append(field_name)
            return None
        if conf < 0.6:
            gaps.append(f"{field_name} (low confidence: {conf:.0%})")
        return winner

    profile = {
        'colours': {
            'primary': resolve(colours_primary, 'primary_colour') or '#000000',
            'secondary': resolve(colours_secondary, 'secondary_colour') or '#666666',
            'accent': resolve(colours_accent, 'accent_colour') or '#0066CC',
        },
        'fonts': {
            'primary': resolve(fonts_primary, 'primary_font') or 'Arial',
            'secondary': resolve(fonts_secondary, 'secondary_font') or 'Arial',
        },
        'layout': {
            'date_format': resolve(date_formats, 'date_format') or 'DD/MM/YYYY',
            'reference_pattern': resolve(ref_patterns, 'reference_pattern'),
            'logo_position': resolve(logo_positions, 'logo_position') or 'top-left',
        },
        'gaps': gaps,
        'source_doc_count': len(extractions),
        'generated_at': datetime.now().isoformat(),
    }

    return profile


def run_brand_profiler(client_code):
    """Main: download brand assets, extract, aggregate, upload profile.

    Returns the brand profile dict.
    """
    config = load_client_config(client_code)
    if not config:
        log.error(f"Client config not found for: {client_code}")
        return None

    brand_assets_folder = config.get('folders', {}).get('brand_assets')
    if not brand_assets_folder:
        log.error("No brand_assets folder configured")
        return None

    learning_folder = config.get('folders', {}).get('learning')
    if not learning_folder:
        log.error("No learning folder configured")
        return None

    # SEC-02: Validate client boundary
    validate_client_operation(client_code, brand_assets_folder)
    validate_client_operation(client_code, learning_folder)

    # Download files from brand assets folder
    files = drive_client.list_files(brand_assets_folder)
    if not files:
        log.warning("No files found in brand assets folder")
        # Create empty profile with all gaps
        profile = {
            'colours': {'primary': None, 'secondary': None, 'accent': None},
            'fonts': {'primary': None, 'secondary': None},
            'layout': {'date_format': None, 'reference_pattern': None, 'logo_position': None},
            'gaps': ['All fields — no brand documents provided'],
            'source_doc_count': 0,
            'generated_at': datetime.now().isoformat(),
        }
        drive_client.upload_or_update_json(learning_folder, 'brand-profile.json', profile)
        return profile

    log.info(f"Found {len(files)} files in brand assets folder")

    extractions = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in files:
            log.info(f"Processing: {f['name']}")
            local_path = os.path.join(tmpdir, f['name'])
            try:
                drive_client.download_file(f['id'], local_path)
                extraction = extract_brand_from_document(local_path, client_code)
                extractions.append(extraction)
                log.info(f"  Extracted brand data from {f['name']}")
            except Exception as e:
                log.warning(f"  Failed to process {f['name']}: {e}")

    if not extractions:
        log.error("No documents could be processed")
        return None

    # Aggregate with consensus logic
    profile = aggregate_profiles(extractions)

    # Upload to 07-LEARNING
    drive_client.upload_or_update_json(learning_folder, 'brand-profile.json', profile)
    log.info("Brand profile uploaded to 07-LEARNING")

    # Update client config
    config_path = PROJECT_ROOT / 'config' / 'clients' / f'{client_code.lower()}.json'
    if not config_path.exists():
        config_path = PROJECT_ROOT / 'config' / 'clients' / f'{client_code}.json'
    if config_path.exists():
        with open(config_path, 'r') as cf:
            client_data = json.load(cf)
        if 'brand' not in client_data:
            client_data['brand'] = {}
        client_data['brand']['profile_generated'] = True
        client_data['brand']['primary_color'] = profile['colours']['primary']
        client_data['brand']['secondary_color'] = profile['colours']['secondary']
        client_data['brand']['font'] = profile['fonts']['primary']
        with open(config_path, 'w') as cf:
            json.dump(client_data, cf, indent=2)
        log.info("Client config updated")

    # Print summary
    print(f"\n{'='*50}")
    print(f"Brand Profile — {config.get('client_name', client_code)}")
    print(f"{'='*50}")
    print(f"Documents analysed: {profile['source_doc_count']}")
    print(f"Primary colour:     {profile['colours']['primary']}")
    print(f"Secondary colour:   {profile['colours']['secondary']}")
    print(f"Primary font:       {profile['fonts']['primary']}")
    print(f"Date format:        {profile['layout']['date_format']}")
    print(f"Reference pattern:  {profile['layout'].get('reference_pattern', 'N/A')}")
    if profile['gaps']:
        print(f"\nGaps requiring client input:")
        for gap in profile['gaps']:
            print(f"  - {gap}")
    print(f"{'='*50}")

    return profile


def main():
    parser = argparse.ArgumentParser(description='Skill 1: Brand Profiler')
    parser.add_argument('client_code', help='Client code (e.g. GILM)')
    args = parser.parse_args()
    run_brand_profiler(args.client_code)


if __name__ == '__main__':
    main()
