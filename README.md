# Compendium Scribe

Compendium Scribe is a Python package that provides uses AI to assemble detailed information about a particular domain into a knowledge base that can be stored and subjected to further processing (such as semantic analysis).

## The Nature of a Compendium

Conceptually, a Compendium is a collection of information that is organized and categorized in a way that makes it easy to find and retrieve specific pieces of information. The goal of such retrieval is in the augmentation of prompts for LLMs, to implement sophisticated forms of in-context learning.

A Compendium is a knowledge graph with a heavy mixing in of retrieval-specialized metadata. A Compendium can be serialized into an XML file or a markdown file.

Compendium Scribe builds Compendia in a way that is tailored to the specific needs of AI applications. The structure of a Compendium created by Compendium Scribe is relational, topic-segmented, keyword-tagged, and associated with relevant questions, allowing for easy semantic embedding of individual concepts as well was fast retrieval of related concepts.

Compendia are not intended to be consumed by human beings, though they may be.

## Compendium Structure

A compendium is modeled in memory using a tree-like structure. The root node of the tree is the Domain, which has Topics and a Summary. Topics in turn have Concept nodes, and their own Topic Summary. Each Concept has various nodes associated with it containing metadata and content.

Imagined as XML, the structure of a Compendium looks like this:

```xml
<domain name="Cell Biology" id="CellBiology">
  <summary><![CDATA[Cells are the basic units of life...]]></summary>
  <topic name="Cell Function" id="CellFunction">
    <topic_summary><![CDATA[Cells have a wide range of functions...]]></topic_summary>
    <concepts>
      <concept name="Functions Perfomed By Cells">
        <questions>
          <question>What functions do cells perform?</question>
          <question>How do cells contribute to the organism's survival?</question>
        </questions>
        <keywords>
          <keyword>cell</keyword>
          <keyword>function</keyword>
        </keywords>
        <relations>
          <prerequisite>compendium://CellBiology/CellStructure</prerequisite>
          <related type="builds upon">compendium://Biology/Genetics/DNA</related>
        </relations>
        <content><![CDATA[Cells perform various functions necessary for the organism's survival...]]></content>
      </concept>
      ...
    </concepts>
  </topic>
  <topic name="Cell Structure" id="CellStructure">
    ...
  </topic>
  ...
</domain>
```

Note that a Compendium is, itself, scoped to a single Domain. The Domain is the root of the tree, and the Compendium is the entire tree.

The `summary` element is a brief summary of the domain, which is used to provide a high-level overview of the domain.

Each Topic and Domain has a unique ID, which is used to reference the topic or domain in other parts of the Compendium or in other Compendia. Reference addresses to other topics are constructed hierarchically based on the tree location, using the `compendium://` scheme.

Topics have their own `summary` element, which is a brief summary of the Topic. Each Topic also has a list of `concepts`, which are the individual ideas and aspects that make up the Topic. These concepts are the atomic units of information that are used to build the Compendium, and include a variety of metadata, such as questions and keywords, to help them be retrieved when needed.

Note that references can be to topics that are not in the same Compendium as the topic referencing them.

## The Process of Creating a Compendium

Creating a Compendium is a process that uses a specific, structured AI pipeline. This process relies on LLMs and the ability to search the Web for relevant information.

There are two modes of Compendium creation: "from scratch" and "deeper study".

### The "from scratch" workflow

Here is the "from scratch" workflow:

1. A Domain is provided, which is what the Compendium will be about.
2. An LLM is used to enhance the provided Domain.
3. An LLM is used to create a comprehensive list of Topics to Research that are relevant to achieving expertise in the Domain.
4. For each Topic to Research:
    1. A Topic object is created.
    2. An LLM is used to create a collection of Research Questions.
    3. For each of the Research Questions:
        1. Use an online-enabled LLM (such as Perplexity) to answer the Research Question.
        2. An LLM is used to create a Concept Name for the answer.
        3. The Concept Name is used to create a Concept in the Topic, using the answer as the Concept content.
        4. Use an LLM to generate all of the metadata for the Concept. Each Concept has:
          - A `questions` section, which is a list of questions that the Topic would address. Notably, the original Research Question is also included here.
          - A `keywords` section, which is a list of keywords associated with the Concept.
          - A `prerequisites` section, which is a list of keywords for ideas that should be understood in order to understand the Concept.
    4. Use an LLM to generate a `topic_summary` for the Topic, based on the contents of all of the Concepts in the Topic.
5. Use an LLM to produce a `summary` for the domain, based on the contents of all of the Concepts in all of the Topics.

### The "deeper study" workflow

The "deeper study" workflow starts with an existing Compendium and adds a deeper subdomain to it. Here is the "deeper study" workflow:

(details TBD)

## The Compendium-Building Interface

The Compendium Scribe is implemented as a Python library that can be used either from within code or as a command-line utility.

### In Code

If used in code, Compendium Scribe will assume the API keys needed are available in the environment variables. Usage is simple and straightforward:

```python
from compendiumscribe import create_compendium

create_compendium(domain="flutes, both traditional and modern")
```

### CLI

When used as a CLI, Compendium Scribe will assume the API keys needed are available in the current environment. Usage is simple and straightforward:

```zsh
compendium-scribe-create-compendium --domain "flutes, both traditional and modern"
```
