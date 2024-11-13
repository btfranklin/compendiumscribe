# Compendium Scribe

Compendium Scribe is a Python package that provides uses AI to assemble detailed information about a particular domain into a knowledge base that can be stored and subjected to further processing (such as semantic analysis).

## The Nature of a Compendium

Conceptually, a Compendium is a collection of information that is organized and categorized in a way that makes it easy to find and retrieve specific pieces of information. The goal of such retrieval is in the augmentation of prompts for LLMs, to implement sophisticated forms of in-context learning.

A Compendium is a knowledge graph with a heavy mixing in of retrieval-specialized metadata. A Compendium can be serialized into an XML file or a markdown file.

Compendium Scribe builds Compendia in a way that is tailored to the specific needs of AI applications. The structure of a Compendium created by Compendium Scribe is relational, topic-segmented, keyword-tagged, and associated with relevant questions, allowing for easy semantic embedding of individual topics as well was fast retrieval of related topics.

Compendia are not intended to be consumed by human beings, though they may be.

## Compendium Structure

A compendium is modeled in memory using a tree-like structure. Nodes in the tree are Domains, which have Topics and Subdomains (which are structurally just Domains). There is also various metadata associated with each Domain and Topic.

Imagined as XML, the structure of a Compendium looks like this:

```xml
<domain name="Cell Biology" id="CellBiology">
  <summary><![CDATA[Cells are the basic units of life...]]></summary>
  <topic name="Cell Function" id="CellFunction">
    <content><![CDATA[Cells perform various functions necessary for the organism's survival...]]></content>
    <keywords>
      <keyword>cell</keyword>
      <keyword>function</keyword>
    </keywords>
    <questions>
      <question>What functions do cells perform?</question>
      <question>How do cells contribute to the organism's survival?</question>
    </questions>
    <relations>
      <prerequisite>compendium://CellBiology/CellStructure</prerequisite>
      <related type="builds upon">compendium://Biology/Genetics/DNA</related>
    </relations>
  </topic>
  <topic name="Cell Structure" id="CellStructure">
    ...
  </topic>
  ...
  <domain name="Mitochondria" id="Mitochondria">
    <summary><![CDATA[Mitochondria are the powerhouses of the cell...]]></summary>
    <topic name="Mitochondrial Structure" id="MitochondrialStructure">
      ...
    </topic>
    ...
  </domain>
  ...
</domain>
```

Note that a Compendium is, itself, scoped to a single Domain. The Domain is the root of the tree, and the Compendium is the entire tree.

Subdomains are structurally just Domains, and are not explicitly identified as subdomains in the XML.

The `summary` element is a brief summary of the topic or domain, which is used to provide a high-level overview of the topic or domain.

Each Topic and Domain has a unique ID, which is used to reference the topic or domain in other parts of the Compendium. Reference addresses to other topics are constructed hierarchically based on the tree location, using the `compendium://` scheme.

Note that references can be to topics that are not in the same domain as the topic referencing them, and may not even be in the same Compendium.

A Topic should be thought of as a single semantically-related unit of information, no more than about a paragraph long.

## The Process of Creating a Compendium

Creating a Compendium is a process that uses a specific, structured AI pipeline. This process relies on LLMs and the ability to search the Web for relevant information.

There are two modes of Compendium creation: "from scratch" and "deeper study".

### The "from scratch" workflow

Here is the "from scratch" workflow:

1. A Domain is provided, which is what the Compendium will be about.
2. An LLM is used to enhance the provided Domain.
3. An LLM is used to create a comprehensive list of Areas of Research that are relevant to achieving expertise in the Domain.
4. For each Area of Research:
    1. An LLM is used to create a collection of Research Questions.
    2. For each of the Research Questions:
        1. Use an online-enabled LLM (such as Perplexity or SearchGPT) to answer the Research Question.
        2. Add the provided question and answer to the Research Findings for the Area of Research. The Research Findings are just one big XML string divided into blocks, with each block representing the answer to a single question.
5. Use an LLM that is strong at summarizing (such as GPT-4o) to analyze the Research Findings and generate a structured list of Topics. Store the planned structure in memory as placeholders to facilitate the next steps.
6. Use a reasoning-specialized LLM (such as o1) to generate all of the Topics, using the Research Findings as context. Each Topic has:
    - A `content` section, which is the main text of the Topic.
    - A `keywords` section, which is a list of keywords associated with the Topic.
    - A `questions` section, which is a list of questions that the Topic would address.
    - A `prerequisites` section, which is a list of prerequisites that should be understood in order to understand the Topic. These are references to other Topics in the Compendium or in other Compendia (if known).
7. Use an LLM to produce a `summary` for the domain, based on the contents of all of the Topics.

### The "deeper study" workflow

The "deeper study" workflow starts with an existing Compendium and adds a deeper subdomain to it. Here is the "deeper study" workflow:

1. A Domain is provided, which is what the Compendium will be about. A container Domain is also provided, which is the existing Compendium to be extended. This Domain will be an in-memory representation, using Topic and Domain objects.
2. An LLM is used to enhance the provided Domain.
3. An LLM is used to create a comprehensive list of Areas of Research that are relevant to achieving expertise in the Domain, using the existing parent Domain's `summary` and Topics as context.
4. From here, the process is the same as the "from scratch" workflow. The new Domain is added to the parent Domain as a subtree.

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
