from __future__ import annotations

from pathlib import Path

from .models import IdeaReportRequest


CLAIMS_QUERIES_SCHEMA_HELP = """You must write valid UTF-8 JSONL files with these exact field contracts.

claims.jsonl records:
- claim_id: string like C01
- section: short string
- source_lines: string
- claim_text: concise claim or target reference description
- claim_type: short string
- priority: high, medium, or low
- short_label: short string
- notes: string, may be empty
- metadata: object

queries.jsonl records:
- query_id: string like C01-Q1
- claim_id: matching existing claim_id
- query_text: focused search query
- short_label: short string
- core_keywords: array of strings
- notes: string, may be empty
- metadata: object
"""


def build_idea_generation_prompt(workspace_dir: Path, request: IdeaReportRequest) -> str:
    constraints = request.constraints.strip() if request.constraints else "None"
    if request.brief and request.brief.strip():
        idea_input_block = f"""User brief:
{request.brief.strip()}

Interpret this brief as a broad research direction.
Infer the likely field, the intended problem, and the most promising innovation angle from the user's description.
Do not follow the wording too mechanically if a sharper research framing is more literature-searchable.
"""
    else:
        idea_input_block = f"""Domain: {request.domain}
Research direction: {request.direction}
Innovation requirements: {request.innovation_requirements}
Constraints: {constraints}
"""
    return f"""You are preparing a workspace for AutoScholar.

Workspace root: {workspace_dir}

Operate only inside this workspace.
Do not modify files outside this workspace.
Write these files and only these files if they need changes:

- inputs/idea_source.md
- artifacts/claims.jsonl
- artifacts/queries.jsonl

Task:
The user wants a research idea report.
Use the following input to create a plausible, literature-searchable research idea package.

{idea_input_block}
Language preference: {request.language}

Requirements for inputs/idea_source.md:
- Write a clear title.
- Include a short summary paragraph.
- Include problem framing, proposed innovation points, expected contribution, risks, and suggested evaluation plan.
- Keep it concrete enough that literature search queries can be derived from it.

Requirements for artifacts/claims.jsonl:
- Create 4 to 6 claims.
- Each claim should represent one searchable problem, evidence need, method hypothesis, or evaluation requirement.
- Make the claims specific and suitable for literature retrieval.

Requirements for artifacts/queries.jsonl:
- Create 1 or 2 focused queries per claim.
- Each query should use terminology likely to work well in Semantic Scholar.
- Keep them concise and targeted.

{CLAIMS_QUERIES_SCHEMA_HELP}

Do not print the JSONL content in the final message.
Write the files directly to disk, then briefly confirm what you created.
"""


def build_reference_lookup_prompt(workspace_dir: Path, source_path: Path, manuscript_path: Path, language: str) -> str:
    return f"""You are preparing a workspace for AutoScholar.

Workspace root: {workspace_dir}

Operate only inside this workspace.
Do not modify files outside this workspace.
Read the source material from:

- {source_path.relative_to(workspace_dir)}
- {manuscript_path.relative_to(workspace_dir)}

Write these files and only these files if they need changes:

- artifacts/claims.jsonl
- artifacts/queries.jsonl

Task:
Recover likely bibliography entries from the uploaded paper source.
The goal is to help AutoScholar generate a references.bib file.

Instructions:
- Identify likely references from the bibliography section, citation markers, title fragments, author-year cues, or TeX citation context.
- Create one claim per target reference to recover.
- Prefer precision over recall.
- Limit the output to the most inferable references rather than inventing uncertain ones.
- If you can infer many references, keep the strongest 10 to 25 targets.

Requirements for artifacts/claims.jsonl:
- Each claim should describe one target paper to recover.
- Use claim_type = "reference_lookup".
- Use short labels that help distinguish entries.

Requirements for artifacts/queries.jsonl:
- Create exactly 1 focused query per claim.
- Query text should combine title keywords, author surnames, year, venue, or method terms when available.
- Each query should maximize the chance of retrieving the exact cited paper.

Language preference for notes: {language}

{CLAIMS_QUERIES_SCHEMA_HELP}

Do not print the JSONL content in the final message.
Write the files directly to disk, then briefly confirm what you created.
"""


def build_final_idea_report_prompt(workspace_dir: Path, language: str) -> str:
    return f"""You are writing the final user-facing idea report for AutoScholar.

Workspace root: {workspace_dir}

Operate only inside this workspace.
Do not modify files outside this workspace.

Read these workspace files before writing:

- inputs/idea_source.md
- artifacts/idea_assessment.json
- artifacts/evidence_map.json
- artifacts/selected_citations.jsonl
- reports/feasibility.md

Write exactly one output file:

- reports/final_idea_report.md

Task:
Produce a polished final report for the end user.
The report should be grounded in the retrieved literature and should not invent support that is not present in the workspace artifacts.

Requirements:
- Use Markdown.
- Language: {language}
- Keep the tone professional and helpful.
- Explain the idea clearly for a researcher who wants a practical project direction.
- Treat this as a standalone final deliverable. The user does not know about internal stages, intermediate drafts, or hidden evaluation files.
- Do not use the words "证据" or "evidence" anywhere in the report.
- When referring to supporting literature in the main text, use citation numbers like `[1]`, `[2]`, `[3]` instead of saying "evidence".
- Add a final `## 参考文献` section listing the cited papers in numbered form.
- Only cite papers that appear in `artifacts/selected_citations.jsonl`.
- Do not expose internal labels such as claim ids, review states, confidence scores, or artifact filenames.
- The report should begin from the current literature landscape, not from defending one pre-fixed solution.
- Treat the user's topic as a broad direction. Your job is to infer:
  1. what the literature says the field is currently doing,
  2. what limitations or unresolved tensions remain,
  3. which concrete research directions are most worth pursuing next.
- Prefer a "research status -> limitations -> improvable directions -> recommended project angle" narrative.
- Do not use section titles such as "最强文献锚点", "strongest literature anchors", "核心证据", or anything that sounds like internal synthesis jargon.
- Include:
  1. title
  2. short executive summary
  3. current research status and mainstream approaches in the literature
  4. what remains unsolved, weak, or improvable
  5. the most promising project directions that could be taken from here
  6. the recommended project angle and next steps
- Be honest when the literature support is incomplete.
- Do not include internal debugging notes, tool chatter, or implementation logs.
- Do not write any other files.

When finished, briefly confirm that reports/final_idea_report.md was written.
"""


def build_reviewed_idea_report_prompt(workspace_dir: Path, language: str) -> str:
    return f"""You are acting as an independent reviewer for AutoScholar.

Workspace root: {workspace_dir}

Operate only inside this workspace.
Do not modify files outside this workspace.

Read these workspace files before writing:

- inputs/idea_source.md
- artifacts/idea_assessment.json
- artifacts/evidence_map.json
- artifacts/selected_citations.jsonl
- reports/feasibility.md
- reports/final_idea_report.md

Write exactly one output file:

- reports/final_idea_report_reviewed.md

Task:
Review the current final idea report as an independent evaluator, not as a compliant assistant following the user's framing.
Use the retrieved literature and your own independent reasoning to challenge narrow assumptions, overfitting to the user's keywords, weakly supported claims, and missed but important adjacent directions.
The user will only see this one final report and must not become aware that there was any earlier draft or review stage.

Requirements:
- Use Markdown.
- Language: {language}
- Keep the tone professional, candid, and constructive, but write as a final polished report rather than as review commentary.
- Do not blindly preserve the original framing if the evidence suggests a stronger or safer reframing.
- Do not mention that you are reviewing, revising, re-evaluating, correcting, or rewriting an earlier version.
- Do not use the words "证据" or "evidence" anywhere in the report.
- When referring to literature in the main text, use citation numbers like `[1]`, `[2]`, `[3]`.
- Add a final `## 参考文献` section listing the cited papers in numbered form.
- Only cite papers that appear in `artifacts/selected_citations.jsonl`.
- Do not expose internal labels such as claim ids, review states, confidence scores, artifact filenames, or pipeline stages.
- Start from the literature itself rather than from the user's tentative solution framing.
- Treat the user input as a broad research area, not as a final method statement that must be defended.
- Your final report should answer:
  1. what the literature says the current research status is,
  2. where the real limitations and open gaps are,
  3. which directions look most worth improving,
  4. what concrete project angle should actually be recommended.
- Prefer a "research status -> current limitations -> improvable directions -> recommended angle" narrative over a "here is the proposed solution and why it matters" narrative.
- Do not use section titles such as "最强文献锚点", "strongest literature anchors", "最强研究角度判断", or other meta-analysis wording that feels like internal report jargon.
- Explicitly look for:
  1. hidden assumptions in the user's requested direction
  2. places where the report follows the user's keywords too closely
  3. deeper strategic recommendations that the original report under-emphasized
  4. stronger problem formulations or narrower paper angles suggested by the evidence
- Produce a revised user-facing report, not review notes.
- The revised report should still be readable as a polished final deliverable.
- It should improve the original report by being more independent, more strategically useful, and more honest about where the idea should be reframed or narrowed.
- Include:
  1. title
  2. short executive summary
  3. current research status and mainstream approaches in the literature
  4. what should be reframed, narrowed, or deprioritized
  5. the most promising directions for improvement or innovation
  6. the recommended project angle
  7. main risks, limitations, or unanswered questions
  8. recommended next steps
- Do not include internal debugging notes, tool chatter, or implementation logs.
- Do not write any other files.

When finished, briefly confirm that reports/final_idea_report_reviewed.md was written.
"""
