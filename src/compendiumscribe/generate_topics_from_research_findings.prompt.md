# Generate Topics from Research Findings Prompt

## System Message

You will be provided with research findings collected from various questions and answers within a domain of expertise. Your task is to analyze these findings and generate a structured list of topics that comprehensively covers the domain. The list should be well-organized, avoid redundancy, and include both broad and specific topics.

Please provide the list as a JSON array of topic names.

**Example:**

```json
[
    "Introduction to Flutes",
    "History of Flutes",
    "Modern Flute Construction",
    "Traditional Flute Music",
    "Exotic Flutes Around the World"
]
```

## Conversation

**User:**
Based on the following research findings, generate a structured list of topics that comprehensively covers the domain.

Research Findings:
{research_findings}
