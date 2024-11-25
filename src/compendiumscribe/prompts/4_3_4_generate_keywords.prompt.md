# Generate Keywords Prompt

## System Message

You will be provided with a short article about a concept. Your task is to create a list of keywords for the article. Keywords can technically be phrases, but they should be short and keyword-like if possible. So for example, if the concept is about the history of flutes, the keywords might be "flute", "history of flutes", "musical instruments", etc.

Keywords should address all of the various concepts that are described in the article, including things that are implied by or directly related to the contents of the article, even if they are not explicitly mentioned.

The list should be a JSON array of strings, with each string containing a single keyword or phrase.

Provide only the keywords, without any additional explanation or commentary.

## Conversation

**User:**
{answer}
