# Compendium Scribe

Compendium Scribe is a Python package that provides AI applications with an organized system for creating, analyzing, and retrieving memories.

## The Nature of a Compendium

Conceptually, a Compendium is a collection of information that is organized and categorized in a way that makes it easy to find and retrieve specific pieces of information. The goal of such retrieval is in the augmentation of prompts for LLMs, to implement sophisticated forms of in-context learning.

Compendium Scribe builds Compendia in a way that is tailored to the specific needs of AI applications. The structure of a Compendium created by Compendium Scribe is hierarchical, segmented, keyword-tagged, and associated with relevant questions, allowing for easy semantic embedding of individual sections of text as well was fast retrieval of any level of an associated subtree of sections.

Compendia are not intended to be consumed by human beings, though they may be.

## Compendium Structure

Let's look at an example structure of a Compendium, viewed as a filesystem tree.

```terminal
\Flutes - Traditional and Modern.compendium
    Introduction.md
    Introduction.keywords.md
    Introduction.questions.md
    Introduction.prerequisites.md
    Historical Overview.md
    Historical Overview.keywords.md
    Historical Overview.questions.md
    Historical Overview.prerequisites.md
    \Traditional Flutes.compendium
        Bamboo Flutes.md
        Bamboo Flutes.keywords.md
        Bamboo Flutes.questions.md
        Bamboo Flutes.prerequisites.md
        Native American Style Flutes.md
        Native American Style Flutes.keywords.md
        Native American Style Flutes.questions.md
        Native American Style Flutes.prerequisites.md
        \Japanese Flutes.compendium
            Shinobue.md
            Shinobue.keywords.md
            Shinobue.questions.md
            Shinobue.prerequisites.md
            Shakuhachi.md
            Shakuhachi.keywords.md
            Shakuhachi.questions.md
            Shakuhachi.prerequisites.md
    \Modern Flutes.compendium
        Silver Concert Flutes.md
        Silver Concert Flutes.keywords.md
        Silver Concert Flutes.questions.md
        Silver Concert Flutes.prerequisites.md
        Crystal Flutes.md
        Crystal Flutes.keywords.md
        Crystal Flutes.questions.md
        Crystal Flutes.prerequisites.md
    \Exotic Flutes.compendium
        Bone Flutes.md
        Bone Flutes.keywords.md
        Bone Flutes.questions.md
        Bone Flutes.prerequisites.md
        Antler Flutes.md
        Antler Flutes.keywords.md
        Antler Flutes.questions.md
        Antler Flutes.prerequisites.md
        Experimental Flutes.md
        Experimental Flutes.keywords.md
        Experimental Flutes.questions.md
        Experimental Flutes.prerequisites.md
```

The elements shown above illustrate an application of the core Compendium structure:

```terminal
\Compendium Name.compendium
    Section Name.md
    Section Name.keywords.md
    Section Name.questions.md
    Section Name.prerequisites.md
```

Notably, each subdirectory ends with the `.compendium` extension and is a recursive data structure allowing the entire subtree to be used as a complete Compendium if so desired.

Each Section is a block of text which, if imagined as part of a single flattened markdown file, would be delineated inside one block of some depth of # heading. Broadly speaking, this is typically a short semantic block addressing a particular topic. The `Section Name.md` file contains the actual content, in the following format:

```markdown
# Section Name

The main text of the section is here.

## Subsection Name

Minor subsections that don't merit their own standalone documents can be included in a deeper heading depth. Examples and special case notes might be good uses of this.
```

The `Section Name.keywords.md` file contains a list of identified Keywords from the associated Section. The first line of the file contains the text `# Section Name Keywords`, and the Keywords are below that in a standard markdown bullet list.

The `Section Name.questions.md` file contains a collection of Questions that the Section would answer. The first line of the file contains the text `# Section Name Questions`, and the Questions are below that in a standard markdown bullet list.

The `Section Name.prerequisites.md` file contains a collection of Prerequisites that should be understood in order to understand the Section. The first line of the file contains the text `# Section Name Prerequisites`, and the Prerequisites are below that in a standard markdown bullet list. These Prerequisites may or may not appear elsewhere in the same Compendium, which allows for flexible systems in which multiple Compendia are available to an agent, and topics may need to be cross-referenced at retrieval time.

## Flat Compendium Structure

It is possible to create a "flat" representation of a Compendium as a single markdown file. In this representation, the structure of the Sections is maintained, with the notable difference that as the filesystem tree depth increases, the header depth is increased in the flat representation. Keywords, Questions, and Prerequisites can optionally be omitted from this representation, as well. If they are included, they are simply subsections within their associated Section.

## The Process of Creating a Compendium

Creating a Compendium is a process that uses a specific, structured AI pipeline. This process relies on LLMs and the ability to search the Web for relevant information. Here is the workflow:

1. A Domain of Expertise is provided, which is what the Compendium will be about.
2. An LLM is used to provide some number of Subjects that will provide a comprehensive coverage of the Domain of Expertise.
3. For each of the Subjects:
    1. An LLM is used to create some number of Topic Questions that would need to be answered to fully understand the Subject. (Notably, these are not the same as the Questions that are stored in the Compendium itself. Those are generated later.)
    2. For each of the Topic Questions:
        1. Use an online-enabled LLM (such as Perplexity or SearchGPT) to answer the Topic Question.
        2. Add the provided answer to the Answers Collection for the Subject.
    3. With all of the Topic Questions answered, use an LLM to create a Subject Analysis Document, which is a rewrite of the Answers Collection into a coherent and comprehensive format. At this stage, the LLM is encouraged to contribute its own insights and observations.
    4. Use an LLM to produce a list of Semantic Divisions based on the Subject Analysis Document. Note that the Semantic Divisions can and should be hierarchical, so this is where the subtree structure of the Compendium is defined.
4. For each Subject Analysis Document, iterate over the Semantic Divisions of the Subject Analysis Document and:
    1. Create a subdirectory if appropriate.
    2. Use an LLM to produce a Section file.
    3. Use an LLM to produce the Section Keywords file.
    4. Use an LLM to produce the Section Questions file.
    5. Use an LLM to produce the Section Prerequisites file.

From this process structure, it is possible to imagine the hierarchical shape of Compendium construction in this way:

A *Compendium* -> is about a *Domain of Expertise* -> which has *Subjects* -> which have *Topics* -> which have *Topic Questions*.

Here is the process above represented in Python-like pseudocode for clarity:

```python
def create_compendium(domain_of_expertise: str):
    # Step 1: Define the domain of expertise
    domain = domain_of_expertise

    # Step 2: Use LLM to generate subjects for the domain
    subjects = generate_subjects(domain)

    # Step 3: For each subject
    for subject in subjects:
        # Step 3.1: Use LLM to generate topic questions for the subject
        topic_questions = generate_topic_questions(subject)
        
        # Step 3.2: For each topic question
        answers_collection = []
        for question in topic_questions:
            # Step 3.2.1: Use online-enabled LLM to answer the topic question
            answer = get_answer_from_llm(question)
            # Step 3.2.2: Add the answer to the answers collection for the subject
            answers_collection.append(answer)
        
        # Step 3.3: Use LLM to create a subject analysis document from the answers collection
        subject_analysis_document = create_subject_analysis(answers_collection)
        
        # Step 3.4: Use LLM to produce a list of semantic divisions from the subject analysis document
        semantic_divisions = create_semantic_divisions(subject_analysis_document)
        
        # Step 4: For each semantic division in the subject analysis document
        for division in semantic_divisions:
            # Step 4.1: Create a subdirectory if appropriate
            create_subdirectory_if_needed(division)
            
            # Step 4.2: Use LLM to produce the section file
            section_file = create_section_file(division)
            
            # Step 4.3: Use LLM to produce the section keywords file
            keywords_file = create_keywords_file(division)
            
            # Step 4.4: Use LLM to produce the section questions file
            questions_file = create_questions_file(division)
            
            # Step 4.5: Use LLM to produce the section prerequisites file
            prerequisites_file = create_prerequisites_file(division)
            
    return True
```

## The Compendium-Building Interface

The Compendium Scribe is implemented as a Python library that can be used either from within code or as a command-line utility.

### In Code

If used in code, Compendium Scribe will assume the API keys needed are available in the environment variables. Usage is simple and straightforward:

```python
from compendiumscribe import compile_compendium

compile_compendium(domain="flutes, both traditional and modern")
```

### CLI

When used as a CLI, Compendium Scribe will assume the API keys needed are available in the current environment. Usage is simple and straightforward:

```zsh
compendium-scribe-compile-compendium --outputdir . --topic "flutes, both traditional and modern"
```
