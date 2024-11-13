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

    # Retrieve the output level from the environment variables
    output_level = os.getenv("OUTPUT_LEVEL", "VERBOSE").upper()

    # Validate the output level
    valid_levels = {"SILENT", "NORMAL", "VERBOSE"}
    if output_level not in valid_levels:
        print(
            f"Invalid OUTPUT_LEVEL '{output_level}' in .env. Defaulting to 'VERBOSE'."
        )
        output_level = "VERBOSE"

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

    # Define logging levels
    LOG_LEVELS = {"SILENT": 0, "NORMAL": 1, "VERBOSE": 2}
    current_level = LOG_LEVELS.get(output_level.upper(), 2)  # Default to VERBOSE

    def log(message: str, level: str = "NORMAL"):
        """
        Conditional logging based on the output level.
        """
        level_value = LOG_LEVELS.get(level.upper(), 1)
        if current_level >= level_value:
            print(message)

    log(
        f"{Back.BLUE}{Fore.WHITE} CREATING COMPENDIUM ",
        "VERBOSE",
    )

    # Step 1: Enhance the provided domain of expertise
    enhanced_domain = enhance_domain(llm_client, domain)
    log(f"Enhanced Domain: {enhanced_domain}", "NORMAL")

    # Create the Domain object
    compendium_domain = Domain(name=enhanced_domain)

    # Step 2: Create a comprehensive list of Areas of Research
    areas_of_research = create_areas_of_research(llm_client, enhanced_domain)
    log(f"Areas of Research: {areas_of_research}", "NORMAL")

    # For each Area of Research
    research_findings = []
    for area in areas_of_research:
        log(f"Processing Area of Research: {area}", "VERBOSE")
        # Step 3: Create a collection of Research Questions
        research_questions = create_research_questions(llm_client, domain, area)
        log(f"Research Questions for '{area}': {research_questions}", "VERBOSE")
        area_research_findings = ""
        # Step 4: Answer each Research Question
        for question in research_questions:
            log(f"Answering Question: {question}", "VERBOSE")
            answer = answer_research_question(online_llm_client, question)
            if not answer:
                log(
                    f"{Fore.YELLOW}Failed to answer question: {question}",
                    "NORMAL",
                )
                continue
            # Step 5: Add the question and answer to the Research Findings
            area_research_findings += f"<block><question>{question}</question><answer>{answer}</answer></block>\n"
        research_findings.append(area_research_findings)

    # Combine all research findings
    combined_research_findings = "\n".join(research_findings)

    # Step 6: Generate a structured list of Topics from Research Findings
    topic_names = generate_topics_from_research_findings(
        llm_client, combined_research_findings
    )
    log(f"Generated Topic Names: {topic_names}", "NORMAL")

    # Step 7: Generate detailed Topics
    for topic_name in topic_names:
        log(f"Generating Topic: {topic_name}", "VERBOSE")
        topic = generate_topic(llm_client, topic_name, combined_research_findings)
        compendium_domain.topics.append(topic)

    # Step 8: Generate Domain Summary
    compendium_domain.summary = generate_domain_summary(llm_client, compendium_domain)
    log(f"Domain Summary: {compendium_domain.summary}", "NORMAL")

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
    return enhanced_domain


@cache.checkpoint(exclude_args=["llm_client"])
def create_areas_of_research(llm_client: OpenAI, domain: str) -> list[str]:
    model_name = os.environ.get("CREATE_AREAS_OF_RESEARCH_LLM", "gpt-4o")
    number_of_areas = os.environ.get("NUMBER_OF_AREAS_OF_RESEARCH", "10")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="2_create_areas_of_research.prompt.md",
    )
    structured_prompt.apply_template_values(
        {
            "domain": domain,
            "number_of_areas": number_of_areas,
        }
    )
    messages = structured_prompt.to_chat_completion_messages()
    response = llm_client.chat.completions.create(
        model=model_name,
        messages=messages,
        max_tokens=1000,
        temperature=0.7,
    )
    areas_text = response.choices[0].message.content.strip()
    try:
        areas = json.loads(areas_text)
        if not isinstance(areas, list):
            raise ValueError("Areas of Research should be a list.")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{Fore.RED}Error parsing Areas of Research: {e}")
        areas = []
    return areas


def create_research_questions(llm_client: OpenAI, domain: str, area: str) -> list[str]:
    """
    Generate a list of research questions for a given domain and area.

    Parameters:
    - llm_client (OpenAI): The OpenAI client instance.
    - domain (str): The domain of expertise.
    - area (str): The specific area within the domain.

    Returns:
    - list[str]: A list of research questions.
    """
    model_name = os.environ.get("CREATE_RESEARCH_QUESTIONS_LLM", "gpt-4o")
    number_of_questions = os.environ.get("NUMBER_OF_QUESTIONS_PER_AREA", "10")
    structured_prompt = StructuredPrompt.from_package_resource(
        package="compendiumscribe.prompts",
        resource_name="3_create_research_questions.prompt.md",
    )
    structured_prompt.apply_template_values(
        {
            "domain": domain,
            "area": area,
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
        # Parse the JSON response
        questions_list = json.loads(questions_text)
        if not isinstance(questions_list, list):
            raise ValueError("Research Questions should be a list of objects.")
        questions = []
        for item in questions_list:
            if "question" in item:
                questions.append(item["question"].strip())
            else:
                print(
                    f"{Fore.YELLOW}Warning: Missing 'question' field in one of the items."
                )
        # Ensure the number of questions matches the requested number
        if len(questions) < int(number_of_questions):
            print(
                f"{Fore.YELLOW}Warning: Expected {number_of_questions} questions, but got {len(questions)}."
            )
    except (json.JSONDecodeError, ValueError) as e:
        print(f"{Fore.RED}Error parsing Research Questions for area '{area}': {e}")
        questions = []
    return questions


def answer_research_question(online_llm_client: OpenAI, question: str) -> str:
    if online_llm_client is None:
        print(f"{Fore.RED}Online LLM client not configured. Cannot answer question.")
        return ""

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
    return topics


def generate_topic(
    llm_client: OpenAI, topic_name: str, research_findings: str
) -> Topic:
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
    return summary
