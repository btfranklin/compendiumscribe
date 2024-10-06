# Generate Topic Prompt

## System Message

You will be provided with a topic name and research findings related to a domain of expertise. Your task is to generate detailed information for the topic. Please include the following in JSON format:

- **content**: A comprehensive explanation of the topic, suitable for someone seeking in-depth understanding.
- **keywords**: A list of relevant keywords associated with the topic.
- **questions**: A list of questions that this topic addresses.
- **prerequisites**: A list of topics or concepts that should be understood before approaching this topic.

**Example Output:**

```json
{
    "content": "Flutes are a family of musical instruments in the woodwind group...",
    "keywords": ["flute", "woodwind", "musical instrument", "history of flute"],
    "questions": [
        "What is the history of the flute?",
        "How is a modern flute constructed?"
    ],
    "prerequisites": ["Basic Music Theory", "History of Musical Instruments"]
}
```

Ensure the content is clear, accurate, and well-structured.

## Conversation

**User:**
Using the following research findings, generate detailed information for the topic '{topic_name}'.

Research Findings:
{research_findings}
