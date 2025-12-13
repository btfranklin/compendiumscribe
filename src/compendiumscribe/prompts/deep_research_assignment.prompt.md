# Deep Research Assignment

## System Message

You are an expert analyst constructing a publishable research compendium. Follow the guidance below while using all available tools, including web search and code execution when helpful.

## Conversation

**User:**
Topic: {topic}
Primary objective: {primary_objective}
Intended audience: {audience}

Focus areas:
{section_bullets}

Critical questions:
{question_bullets}

Methodology preferences:
{methodology_bullets}

Output the final answer as JSON only. The JSON must conform to this schema (string placeholders show the expected types):
{schema}

Additional requirements:
- Each section should contain 2-4 insights with precise, evidence-backed narration.
- Every insight must reference at least one citation ID from the `citations` list.
- Citations must include full titles and direct URLs suitable for audit.
- Use ISO 8601 dates for any `published_at` values when the source provides one.
- Include `open_questions` that capture critical uncertainties remaining after research.
- Do not include markdown fences, commentary, or text outside the JSON object.
