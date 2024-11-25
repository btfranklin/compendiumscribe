import sys
import os
import json
import colorama.initialise as colorama
from colorama import Fore, Back
from openai import OpenAI
from dotenv import load_dotenv
from promptdown import StructuredPrompt
from pickled_pipeline import Cache

from .model import Domain, Topic, Concept

cache = Cache()


# Step 1: Provide Domain, which is what the Compendium will be about.
def create_compendium(domain: str) -> Domain:
    """
    Main pipeline for creating a compendium from a given domain.

    Parameters:
    - domain (str): The domain of expertise.
    - output_level (str): The verbosity level of the output. Options are SILENT, NORMAL, VERBOSE.

    Returns:
    - Domain: The created compendium as a Domain object.
    """
    # Load environment variables from .env file
    load_dotenv()

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    perplexity_api_key = os.environ.get("PERPLEXITY_API_KEY")

    if not openai_api_key:
        print(f"{Fore.RED}OPENAI_API_KEY not found in environment variables.")
        sys.exit(1)

    llm_client = OpenAI(api_key=openai_api_key)

    if perplexity_api_key:
        online_llm_client = OpenAI(
            api_key=perplexity_api_key,
            base_url="https://api.perplexity.ai",
        )
    else:
        online_llm_client = None  # Or handle accordingly

    # Initialize colorama
    colorama.init(autoreset=True)

    print(f"{Back.BLUE} CREATING COMPENDIUM ")

    # Step 2: Enhance the provided domain of expertise
    enhanced_domain = enhance_domain(llm_client, domain)

    # Create the Domain object
    compendium_domain = Domain(name=enhanced_domain)

    # Step 3: Create a comprehensive list of Topics to Research
    topics_to_research = create_topics_to_research(llm_client, enhanced_domain)

    # Step 4: For each Topic to Research...
    for topic_to_research in topics_to_research:

        # Step 4.1: Create the Topic object
        topic = Topic(name=topic_to_research)
        compendium_domain.topics.append(topic)

        # Step 4.2: Create a collection of Research Questions
        research_questions = create_research_questions(
            llm_client, enhanced_domain, topic_to_research
        )

        # Step 4.3: For each of the Research Questions...
        for question in research_questions:

            # Step 4.3.1: Answer the Research Question
            answer = answer_research_question(online_llm_client, question)
            if not answer:
                print(f"{Fore.YELLOW}Failed to answer question: {question}")
                continue

            # Step 4.3.2: Use the answer content to generate a Concept Name
            concept_name = generate_concept_name_from_answer(llm_client, answer)

            # Step 4.3.3: Create a Concept in the Topic
            concept = Concept(name=concept_name, content=answer)
            topic.concepts.append(concept)

            # Step 4.3.4: Generate all of the metadata for the Concept

            # Additional Questions
            concept.questions.append(question)
            additional_questions = create_additional_concept_questions(
                llm_client, answer, question
            )
            concept.questions.extend(additional_questions)

            # Keywords
            keywords = generate_keywords(llm_client, answer)
            concept.keywords.extend(keywords)

            # Prerequisites
            prerequisites = generate_prerequisites(llm_client, answer)
            concept.prerequisites.extend(prerequisites)

        # Step 4.4: Genearte Topic Summary
        topic.topic_summary = generate_topic_summary(llm_client, topic)

    # Step 5: Generate Domain Summary
    compendium_domain.summary = generate_domain_summary(llm_client, compendium_domain)

    return compendium_domain


@cache.checkpoint(exclude_args=["llm_client"])
def enhance_domain(llm_client: OpenAI, domain: str) -> str:
    model_name = os.environ.get("ENHANCE_DOMAIN_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="2_enhance_domain.prompt.md",
    )
    structured_prompt.apply_template_values({"domain": domain})
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.2,
        max_tokens=100,
    )
    enhanced_domain = response.choices[0].message.content.strip()
    print(f"{Fore.BLUE}Enhanced Domain:{Fore.RESET} {enhanced_domain}")
    return enhanced_domain


@cache.checkpoint(exclude_args=["llm_client"])
def create_topics_to_research(llm_client: OpenAI, domain: str) -> list[str]:
    model_name = os.environ.get("CREATE_TOPICS_TO_RESEARCH_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="3_create_topics_to_research.prompt.md",
    )
    structured_prompt.apply_template_values(
        {
            "domain": domain,
        }
    )
    messages = structured_prompt.to_chat_completion_messages()

    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=1000,
        temperature=0.7,
    )
    topics_text = response.choices[0].message.content.strip()
    try:
        # If the text is wrapped in ```json...``` format, remove those indicators
        if topics_text.startswith("```json") and topics_text.endswith("```"):
            topics_text = topics_text[7:-3]

        # Parse the JSON response
        topics_to_research = json.loads(topics_text)
        if not isinstance(topics_to_research, list):
            raise ValueError("Topics to Research should be a list.")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{Fore.RED}Error parsing Topics to Research: {e}")
        sys.exit(1)

    print(f"{Fore.BLUE}Topics to Research:{Fore.RESET} {topics_to_research}")
    return topics_to_research


@cache.checkpoint(exclude_args=["llm_client"])
def create_research_questions(llm_client: OpenAI, domain: str, topic: str) -> list[str]:
    """
    Generate a list of research questions for a given domain and topic.

    Parameters:
    - llm_client (OpenAI): The OpenAI client instance.
    - domain (str): The domain of expertise.
    - topic (str): The specific topic within the domain.

    Returns:
    - list[str]: A list of research questions.
    """
    print(
        f"{Fore.BLUE}Creating research questions for Topic to Research:{Fore.RESET} {topic}"
    )

    model_name = os.environ.get("CREATE_RESEARCH_QUESTIONS_LLM", "gpt-4o")
    number_of_questions = os.environ.get("NUMBER_OF_QUESTIONS_PER_AREA", "10")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="4_2_create_research_questions.prompt.md",
    )
    structured_prompt.apply_template_values(
        {
            "domain": domain,
            "topic": topic,
            "number_of_questions": number_of_questions,
        }
    )
    messages = structured_prompt.to_chat_completion_messages()

    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=1000,
        temperature=0.7,
    )
    questions_text = response.choices[0].message.content.strip()
    try:
        # If the text is wrapped in ```json...``` format, remove those indicators
        if questions_text.startswith("```json") and questions_text.endswith("```"):
            questions_text = questions_text[7:-3]

        # Parse the JSON response, which should contain a list of objects that looks like this:
        # [
        #    {"number": 1, "question": "First question"},
        #    {"number": 2, "question": "Second question"},
        #    ...
        # ]
        questions_list = json.loads(questions_text)
        if not isinstance(questions_list, list):
            raise ValueError("Research Questions should be a list of objects.")
        questions = []
        for numbered_question in questions_list:
            if "question" in numbered_question:

                # Get the question string from the object
                question = numbered_question["question"].strip()
                questions.append(question)
            else:
                # Warn if the question is missing
                print(
                    f"{Fore.YELLOW}Warning: Missing 'question' field in one of the items."
                )
        # Warn if the number of questions is less than the requested number
        if len(questions) < int(number_of_questions):
            print(
                f"{Fore.YELLOW}Warning: Expected {number_of_questions} questions, but got {len(questions)}."
            )
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{Fore.RED}Error parsing Research Questions for topic '{topic}': {e}")
        questions = []

    print(f"{Fore.BLUE}Research Questions for '{topic}':")
    for question in questions:
        print(f" - {question}")

    return questions


@cache.checkpoint(exclude_args=["online_llm_client"])
def answer_research_question(online_llm_client: OpenAI, question: str) -> str:
    print(f"{Fore.BLUE}Answering Research Question:{Fore.RESET} {question}")

    if online_llm_client is None:
        print(f"{Fore.RED}Online LLM client not configured. Cannot answer question.")
        sys.exit(1)

    model_name = os.environ.get(
        "ANSWER_RESEARCH_QUESTION_LLM", "llama-3.1-sonar-huge-128k-online"
    )
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="4_3_1_research_and_generate_answer.prompt.md",
    )
    structured_prompt.apply_template_values({"question": question})
    messages = structured_prompt.to_chat_completion_messages()
    try:
        response = online_llm_client.chat.completions.create(
            model=model_name,
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
        )
        answer = response.choices[0].message.content.strip()
        return answer
    except Exception as e:
        print(f"{Fore.RED}Error answering question '{question}': {e}")
        return ""


@cache.checkpoint(exclude_args=["llm_client"])
def generate_concept_name_from_answer(llm_client: OpenAI, answer: str) -> str:
    model_name = os.environ.get("GENERATE_CONCEPT_NAME_FROM_ANSWER_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="4_3_2_generate_concept_name.prompt.md",
    )
    structured_prompt.apply_template_values({"answer": answer})
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.2,
        max_tokens=100,
    )
    concept_name = response.choices[0].message.content.strip()
    print(f"{Fore.BLUE}Concept Name:{Fore.RESET} {concept_name}")
    return concept_name


@cache.checkpoint(exclude_args=["llm_client"])
def create_additional_concept_questions(
    llm_client: OpenAI, answer: str, question: str
) -> list[str]:
    model_name = os.environ.get("CREATE_ADDITIONAL_CONCEPT_QUESTIONS_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="4_3_4_create_additional_concept_questions.prompt.md",
    )
    structured_prompt.apply_template_values({"answer": answer, "question": question})
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7,
        max_tokens=1000,
    )
    additional_questions_text = response.choices[0].message.content.strip()

    try:
        # If the text is wrapped in ```json...``` format, remove those indicators
        if additional_questions_text.startswith(
            "```json"
        ) and additional_questions_text.endswith("```"):
            additional_questions_text = additional_questions_text[7:-3]

        # Parse the JSON response
        additional_questions_list = json.loads(additional_questions_text)
        if not isinstance(additional_questions_list, list):
            raise ValueError("Additional Questions should be a list of strings.")
        additional_questions = []
        for additional_question in additional_questions_list:
            additional_questions.append(additional_question.strip())
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{Fore.RED}Error parsing Additional Questions: {e}")
        additional_questions = []

    print(f"{Fore.BLUE}Additional Questions:")
    for question in additional_questions:
        print(f" - {question}")
    return additional_questions


@cache.checkpoint(exclude_args=["llm_client"])
def generate_keywords(llm_client: OpenAI, answer: str) -> list[str]:
    model_name = os.environ.get("GENERATE_KEYWORDS_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="4_3_4_generate_keywords.prompt.md",
    )
    structured_prompt.apply_template_values({"answer": answer})
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7,
        max_tokens=400,
    )
    keywords_text = response.choices[0].message.content.strip()

    try:
        # If the text is wrapped in ```json...``` format, remove those indicators
        if keywords_text.startswith("```json") and keywords_text.endswith("```"):
            keywords_text = keywords_text[7:-3]

        # Parse the JSON response
        keywords_list = json.loads(keywords_text)
        if not isinstance(keywords_list, list):
            raise ValueError("Keywords should be a list of strings.")
        keywords = []
        for keyword in keywords_list:
            keywords.append(keyword.strip().lower())
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{Fore.RED}Error parsing Keywords: {e}")
        keywords = []

    print(f"{Fore.BLUE}Keywords: {keywords}")
    return keywords


@cache.checkpoint(exclude_args=["llm_client"])
def generate_prerequisites(llm_client: OpenAI, answer: str) -> list[str]:
    model_name = os.environ.get("GENERATE_PREREQUISITES_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="4_3_4_generate_prerequisites.prompt.md",
    )
    structured_prompt.apply_template_values({"answer": answer})
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7,
        max_tokens=1000,
    )
    prerequisites_text = response.choices[0].message.content.strip()

    try:
        # If the text is wrapped in ```json...``` format, remove those indicators
        if prerequisites_text.startswith("```json") and prerequisites_text.endswith(
            "```"
        ):
            prerequisites_text = prerequisites_text[7:-3]

        # Parse the JSON response
        prerequisites_list = json.loads(prerequisites_text)
        if not isinstance(prerequisites_list, list):
            raise ValueError("Prerequisites should be a list of strings.")
        prerequisites = []
        for prerequisite in prerequisites_list:
            prerequisites.append(prerequisite.strip().lower())
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{Fore.RED}Error parsing Prerequisites: {e}")
        prerequisites = []

    print(f"{Fore.BLUE}Prerequisites:")
    for prerequisite in prerequisites:
        print(f" - {prerequisite}")
    return prerequisites


@cache.checkpoint(exclude_args=["llm_client"])
def generate_topic_summary(llm_client: OpenAI, topic: Topic) -> str:
    model_name = os.environ.get("GENERATE_TOPIC_SUMMARY_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="4_4_generate_topic_summary.prompt.md",
    )

    # Generate a concatenated string of all of the Concepts in the Topic,
    # using a markdown format where each Concept's name is a heading and
    # the content is in text following that. Each heading should have a blank
    # line before and after it, so the format looks like this:
    #
    # ## Concept Name
    #
    # Concept content goes here and is in long form...
    #
    # ## Another Concept Name
    #
    # More concept content...
    #
    concepts_markdown = "\n\n".join(
        [f"## {concept.name}\n\n{concept.content}" for concept in topic.concepts]
    )
    structured_prompt.apply_template_values(
        {"topic_name": topic.name, "concepts_markdown": concepts_markdown}
    )
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7,
    )
    summary = response.choices[0].message.content.strip()
    print(f"{Fore.BLUE}Topic Summary:{Fore.RESET} {summary}")
    return summary


@cache.checkpoint(exclude_args=["llm_client"])
def generate_domain_summary(llm_client: OpenAI, domain: Topic) -> str:
    model_name = os.environ.get("GENERATE_DOMAIN_SUMMARY_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="5_generate_domain_summary.prompt.md",
    )

    # Generate a concatenated string of all of the Topic summaries in the Domain,
    # using a markdown format where each Topic's name is a heading and
    # the summary is in text following that. Each heading should have a blank
    # line before and after it, so the format looks like this:
    #
    # ## Topic Name
    #
    # The summary of the topic goes here and is in long form...
    #
    # ## Another Topic Name
    #
    # More topic summary content...
    #
    topic_summaries_markdown = "\n\n".join(
        [f"## {topic.name}\n\n{topic.topic_summary}" for topic in domain.topics]
    )
    structured_prompt.apply_template_values(
        {
            "domain_name": domain.name,
            "topic_summaries_markdown": topic_summaries_markdown,
        }
    )
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0.7,
    )
    summary = response.choices[0].message.content.strip()
    print(f"{Fore.BLUE}Domain Summary:{Fore.RESET} {summary}")
    return summary
