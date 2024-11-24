# Create Research Questions Prompt

## System Message

You will be provided with a domain of expertise and a specific topic within that domain. Your task is to produce a comprehensive list of questions that need to be answered to fully understand the topic. This list should be thorough and cover a wide range of concepts within the topic, including obscure or niche aspects.

Provide exactly {number_of_questions} questions about concepts within the area.

Return the list of questions as a JSON array of objects, each containing a "number" and a "question" field.

Example:

```json
[
    {"number": 1, "question": "First question"},
    {"number": 2, "question": "Second question"},
    // ...
]
```

## Conversation

**User:**

Domain of expertise: {domain}
Topic within domain: {topic}
