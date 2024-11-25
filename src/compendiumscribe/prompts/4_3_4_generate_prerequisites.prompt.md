# Generate Prerequisites Prompt

## System Message

You will be provided with a short article about a concept. Your task is to create a list of prerequisites for the concept. Prerequisites are concepts that are necessary for understanding the concept, but are not explicitly stated in the article. These are concepts that would be an absolute requirement for understanding the concept in the article, not just related topics.

The list should be a JSON array of strings, with each string containing a single prerequisite concept. A single prerequisite concept can be a single word, or a phrase, or a concept name.

Provide only the prerequisites, without any additional explanation or commentary.

## Conversation

**User:**
{answer}
