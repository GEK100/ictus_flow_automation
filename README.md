# Ictus Flow System

AI-powered document processing service for SMEs and charities.

## Quick Start

1. Copy `.env.example` to `.env` and fill in your API keys
2. Install Python dependencies: `pip install -r requirements.txt`
3. Install Node dependencies: `npm install`
4. Run: `python scripts/drive_watcher.py`

## Architecture

- **Prompts:** `prompts/` — one per workflow, Layer 1 (base) instructions
- **Handlers:** `scripts/handlers/` — one per workflow, processes classified files
- **Skills:** `scripts/skills/` — intelligence layer (brand profiling, QA, corrections, learning)
- **Learning:** `learning/` — shared intelligence across clients (Tier 2 industry, Tier 3 universal)
- **Client data:** Google Drive per client, config in `config/clients/`

## Prompt Assembly (4 layers)

1. Base prompt from `prompts/[workflow].txt`
2. Industry corrections from `learning/industry/[vertical]/corrections.json`
3. Client corrections from client's `07-LEARNING/corrections.json` on Drive
4. Brand + tone from client's `brand-profile.json` and `tone-profile.json` (output workflows only)

## Key Files

- `SKILLS_SPEC.md` — Full specification for all 10 intelligence layer skills
- `scripts/utils/prompt_builder.py` — Assembles the 4-layer prompts at runtime
- `config/workflows/routing-rules.json` — Maps classifications to handlers

## Build Order

See SKILLS_SPEC.md for the skill implementation order.
For workflows, build invoice processing first, then follow the Build Guide phases.
