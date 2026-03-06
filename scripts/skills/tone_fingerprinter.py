"""Skill 2: Tone Fingerprinter.

Analyses client correspondence to extract communication voice:
formality, sentence length, vocabulary, salutations, signoffs, jargon.

Usage:
    python scripts/skills/tone_fingerprinter.py <client_code>
"""

import os
import sys
import json
import argparse
import shutil
import uuid
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


def extract_tone_from_document(filepath, client_code):
    """Send a single document to Sonnet for tone analysis.

    Returns dict with tone fields.
    """
    system_prompt = load_base_prompt('tone-fingerprinter.txt')

    ext = Path(filepath).suffix.lower()
    if ext == '.pdf':
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                text = ''
                for page in pdf.pages[:5]:
                    text += (page.extract_text() or '') + '\n'
        except Exception:
            text = ''
    elif ext == '.docx':
        from docx import Document
        doc = Document(filepath)
        text = '\n'.join(p.text for p in doc.paragraphs)
    else:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()

    if not text.strip():
        return None

    prompt = f"Analyse the tone and communication style of this correspondence:\n\n{text[:5000]}"

    return claude_client.send_message_json(
        prompt=prompt,
        system_prompt=system_prompt,
        model_tier='MODEL_STANDARD',
        max_tokens=1500,
        client_code=client_code,
        workflow='tone-fingerprinter',
    )


def aggregate_tone_profiles(analyses):
    """Aggregate multiple tone analyses into a single profile.

    Averages numerical fields, takes mode of categorical fields.
    """
    formality_scores = []
    sentence_lengths = []
    vocabulary_levels = []
    salutations = []
    signoffs = []
    voices = []
    jargon_levels = []
    all_phrases = []
    all_anti_patterns = []

    for a in analyses:
        if not a:
            continue
        if a.get('formality') is not None:
            formality_scores.append(a['formality'])
        if a.get('sentence_length'):
            sentence_lengths.append(a['sentence_length'])
        if a.get('vocabulary_complexity'):
            vocabulary_levels.append(a['vocabulary_complexity'])
        if a.get('salutation'):
            salutations.append(a['salutation'])
        if a.get('signoff'):
            signoffs.append(a['signoff'])
        if a.get('voice'):
            voices.append(a['voice'])
        if a.get('jargon_level'):
            jargon_levels.append(a['jargon_level'])
        if a.get('characteristic_phrases'):
            all_phrases.extend(a['characteristic_phrases'])
        if a.get('anti_patterns'):
            all_anti_patterns.extend(a['anti_patterns'])

    def mode(values):
        if not values:
            return None
        return Counter(values).most_common(1)[0][0]

    # Characteristic phrases: appearing in 3+ samples (or 30%+ of samples)
    phrase_threshold = max(3, len(analyses) * 0.3)
    phrase_counts = Counter(all_phrases)
    char_phrases = [p for p, c in phrase_counts.items() if c >= phrase_threshold]

    # Anti-patterns: never used across all samples
    anti_pattern_counts = Counter(all_anti_patterns)
    anti_patterns = [p for p, c in anti_pattern_counts.items()
                     if c >= max(2, len(analyses) * 0.5)]

    profile = {
        'formality': round(sum(formality_scores) / len(formality_scores)) if formality_scores else 3,
        'sentence_length': mode(sentence_lengths) or 'medium',
        'vocabulary_complexity': mode(vocabulary_levels) or 'plain',
        'salutation': mode(salutations) or 'Hi [Name]',
        'signoff': mode(signoffs) or 'Kind regards',
        'voice': mode(voices) or 'active',
        'jargon_level': mode(jargon_levels) or 'moderate',
        'characteristic_phrases': char_phrases[:10],
        'anti_patterns': anti_patterns[:10],
        'source_doc_count': len(analyses),
        'generated_at': datetime.now().isoformat(),
    }

    return profile


def run_tone_fingerprinter(client_code):
    """Main: download correspondence, analyse, aggregate, upload profile.

    Returns the tone profile dict.
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

    # Download correspondence samples
    files = drive_client.list_files(brand_assets_folder)
    if not files:
        log.warning("No files found for tone analysis")
        profile = {
            'formality': None, 'sentence_length': None,
            'vocabulary_complexity': None, 'salutation': None,
            'signoff': None, 'voice': None, 'jargon_level': None,
            'characteristic_phrases': [], 'anti_patterns': [],
            'source_doc_count': 0, 'generated_at': datetime.now().isoformat(),
        }
        drive_client.upload_or_update_json(learning_folder, 'tone-profile.json', profile)
        return profile

    log.info(f"Found {len(files)} files for tone analysis")

    analyses = []
    tmpdir = os.path.join(
        os.environ.get('TEMP', '/tmp'), 'ictus-flow-processing',
        f'tone-fingerprinter-{uuid.uuid4().hex[:8]}',
    )
    os.makedirs(tmpdir, exist_ok=True)
    try:
        for f in files:
            log.info(f"Analysing: {f['name']}")
            local_path = os.path.join(tmpdir, f['name'])
            try:
                drive_client.download_file(f['id'], local_path)
                analysis = extract_tone_from_document(local_path, client_code)
                if analysis:
                    analyses.append(analysis)
                    log.info(f"  Formality: {analysis.get('formality')}, "
                             f"Voice: {analysis.get('voice')}")
            except Exception as e:
                log.warning(f"  Failed to analyse {f['name']}: {e}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    if not analyses:
        log.error("No documents could be analysed for tone")
        return None

    # Aggregate
    profile = aggregate_tone_profiles(analyses)

    # Upload to 07-LEARNING
    drive_client.upload_or_update_json(learning_folder, 'tone-profile.json', profile)
    log.info("Tone profile uploaded to 07-LEARNING")

    # Update client config
    config_path = PROJECT_ROOT / 'config' / 'clients' / f'{client_code.lower()}.json'
    if not config_path.exists():
        config_path = PROJECT_ROOT / 'config' / 'clients' / f'{client_code}.json'
    if config_path.exists():
        with open(config_path, 'r') as cf:
            client_data = json.load(cf)
        if 'tone' not in client_data:
            client_data['tone'] = {}
        client_data['tone']['profile_generated'] = True
        client_data['tone']['formality'] = profile['formality']
        with open(config_path, 'w') as cf:
            json.dump(client_data, cf, indent=2)
        log.info("Client config updated")

    # Print summary
    print(f"\n{'='*50}")
    print(f"Tone Profile — {config.get('client_name', client_code)}")
    print(f"{'='*50}")
    print(f"Documents analysed: {profile['source_doc_count']}")
    print(f"Formality:          {profile['formality']}/5")
    print(f"Sentence length:    {profile['sentence_length']}")
    print(f"Vocabulary:         {profile['vocabulary_complexity']}")
    print(f"Salutation:         {profile['salutation']}")
    print(f"Sign-off:           {profile['signoff']}")
    print(f"Voice:              {profile['voice']}")
    print(f"Jargon level:       {profile['jargon_level']}")
    if profile['characteristic_phrases']:
        print(f"Phrases:            {', '.join(profile['characteristic_phrases'])}")
    if profile['anti_patterns']:
        print(f"Anti-patterns:      {', '.join(profile['anti_patterns'])}")
    print(f"{'='*50}")

    return profile


def main():
    parser = argparse.ArgumentParser(description='Skill 2: Tone Fingerprinter')
    parser.add_argument('client_code', help='Client code (e.g. GILM)')
    args = parser.parse_args()
    run_tone_fingerprinter(args.client_code)


if __name__ == '__main__':
    main()
