# Create Additional Concept Questions Prompt

## System Message

You will be provided with a short article about a concept, and an example question that the article would be used to answer. Your task is to create a list of additional questions that the article would be useful for answering.

These questions can be related to the original question, but do not have to be. They can address any question that is answered by the article.

The list should be a JSON array of strings, with each string containing a single question.

## Conversation

**User:**
<article>
{answer}
</article>

<example_question>{question}</example_question>
