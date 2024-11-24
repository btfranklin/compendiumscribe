import re
import sys
import os
import json
import colorama.initialise as colorama
from colorama import Fore, Back
from openai import OpenAI
from dotenv import load_dotenv
from promptdown import StructuredPrompt
from pickled_pipeline import Cache

from .model import Domain, Topic

cache = Cache()


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

    # Step 1: Enhance the provided domain of expertise
    enhanced_domain = enhance_domain(llm_client, domain)

    # Create the Domain object
    compendium_domain = Domain(name=enhanced_domain)

    # Step 2: Create a comprehensive list of Topics to Research
    topics_to_research = create_topics_to_research(llm_client, enhanced_domain)

    # For each Topic
    questions_and_answers: list[list[tuple[str, str]]] = []
    for topic in topics_to_research:
        # Step 3: Create a collection of Research Questions
        research_questions = create_research_questions(
            llm_client, enhanced_domain, topic
        )
        topic_questions_and_answers: list[tuple[str, str]] = []
        # Step 4: Answer each Research Question
        for question in research_questions:
            answer = answer_research_question(online_llm_client, question)
            if not answer:
                print(f"{Fore.YELLOW}Failed to answer question: {question}")
                continue
            # Record the question and answer
            topic_questions_and_answers += [(question, answer)]
        questions_and_answers.append(topic_questions_and_answers)

    # Step 6: Generate a structured list of Topics from Research Findings
    # topic_names = generate_topics_from_research_findings(
    #     llm_client, combined_research_findings
    # )

    # Step 7: Generate detailed Topics
    # for topic_name in topic_names:
    #     topic = generate_topic(llm_client, topic_name, combined_research_findings)
    #     compendium_domain.topics.append(topic)

    # Step 8: Generate Domain Summary
    compendium_domain.summary = generate_domain_summary(llm_client, compendium_domain)

    return compendium_domain


@cache.checkpoint(exclude_args=["llm_client"])
def enhance_domain(llm_client: OpenAI, domain: str) -> str:
    model_name = os.environ.get("ENHANCE_DOMAIN_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="1_enhance_domain.prompt.md",
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
        resource_name="2_create_topics_to_research.prompt.md",
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
        response_format=list[str],
    )
    areas_text = response.choices[0].message.content.strip()
    try:
        # If the text is wrapped in ```json...``` format, remove those indicators
        if areas_text.startswith("```json") and areas_text.endswith("```"):
            areas_text = areas_text[7:-3]

        # Parse the JSON response
        areas_of_research = json.loads(areas_text)
        if not isinstance(areas_of_research, list):
            raise ValueError("Areas of Research should be a list.")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{Fore.RED}Error parsing Areas of Research: {e}")
        sys.exit(1)

    print(f"{Fore.BLUE}Areas of Research:{Fore.RESET} {areas_of_research}")
    return areas_of_research


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
        resource_name="3_create_research_questions.prompt.md",
    )
    structured_prompt.apply_template_values(
        {
            "domain": domain,
            "topic": topic,
            "number_of_questions": number_of_questions,
        }
    )
    messages = structured_prompt.to_chat_completion_messages()

    # Define a class that will allow a response in this format:
    # [
    #    {"number": 1, "question": "First question"},
    #    {"number": 2, "question": "Second question"},
    # ]
    class Question:
        number: int
        question: str

    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=1000,
        temperature=0.7,
        response_format=list[Question],
    )
    questions_text = response.choices[0].message.content.strip()
    try:
        # If the text is wrapped in ```json...``` format, remove those indicators
        if questions_text.startswith("```json") and questions_text.endswith("```"):
            questions_text = questions_text[7:-3]

        # Parse the JSON response
        questions_list = json.loads(questions_text)
        if not isinstance(questions_list, list):
            raise ValueError("Research Questions should be a list of objects.")
        questions = []
        for item in questions_list:
            if "question" in item:
                questions.append(item["question"].strip())
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

    print(f"{Fore.BLUE}Research Questions for '{topic}':{Fore.RESET} {questions}")

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
        resource_name="4_research_and_generate_answer.prompt.md",
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


def generate_topics_from_research_findings(
    llm_client: OpenAI, research_findings: str
) -> list[str]:
    model_name = os.environ.get(
        "GENERATE_TOPICS_FROM_RESEARCH_FINDINGS_LLM", "o1-preview"
    )
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="6_generate_topics_from_research_findings.prompt.md",
    )
    structured_prompt.apply_template_values({"research_findings": research_findings})
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=1500,
        temperature=0.7,
    )
    topics_text = response.choices[0].message.content.strip()
    try:
        topics = json.loads(topics_text)
        if not isinstance(topics, list):
            raise ValueError("Topics should be a list.")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{Fore.RED}Error parsing Topics: {e}")
        topics = []

    print(f"{Fore.BLUE}Generated Topic Names:{Fore.BLUE} {topics}")

    return topics


def generate_topic(
    llm_client: OpenAI, topic_name: str, research_findings: str
) -> Topic:
    print(f"{Fore.BLUE}Generating Topic:{Fore.RESET} {topic_name}")

    model_name = os.environ.get("GENERATE_TOPIC_LLM", "gpt-4o")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="7_generate_topic.prompt.md",
    )
    structured_prompt.apply_template_values(
        {"topic_name": topic_name, "research_findings": research_findings}
    )
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=1500,
        temperature=0.7,
    )
    topic_text = response.choices[0].message.content.strip()
    try:
        topic_data = json.loads(topic_text)
    except json.JSONDecodeError as e:
        print(f"{Fore.RED}Error parsing topic data for '{topic_name}': {e}")
        topic_data = {}
    topic = Topic(
        name=topic_name,
        content=topic_data.get("content", ""),
        keywords=topic_data.get("keywords", []),
        questions=topic_data.get("questions", []),
        prerequisites=topic_data.get("prerequisites", []),
    )
    return topic


def generate_domain_summary(llm_client: OpenAI, compendium_domain: Domain) -> str:
    model_name = os.environ.get("GENERATE_DOMAIN_SUMMARY_LLM", "gpt-4o")
    topics_content = "\n".join([topic.content for topic in compendium_domain.topics])
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="8_generate_domain_summary.prompt.md",
    )
    structured_prompt.apply_template_values(
        {"domain_name": compendium_domain.name, "topics_content": topics_content}
    )
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=500,
        temperature=0.7,
    )
    summary = response.choices[0].message.content.strip()

    print(f"{Fore.BLUE}Domain Summary:{Fore.RESET} {compendium_domain.summary}")

    return summary
