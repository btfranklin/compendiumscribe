from compendiumscribe.model import Domain, Topic, Concept, etree_to_string


def elements_equal(e1, e2):
    """
    Helper function to compare two XML elements.
    """
    if e1.tag != e2.tag:
        return False
    if (e1.text or "").strip() != (e2.text or "").strip():
        return False
    if e1.attrib != e2.attrib:
        return False
    if len(e1) != len(e2):
        return False
    return all(elements_equal(c1, c2) for c1, c2 in zip(e1, e2))


def test_concept_to_xml():
    concept = Concept(
        name="Functions Performed By Cells",
        keywords=["cell", "function"],
        questions=[
            "What functions do cells perform?",
            "How do cells contribute to the organism's survival?",
        ],
        prerequisites=["basic biology", "cells"],
        content="Cells perform various functions necessary for the organism's survival...",
    )

    expected_xml = """<concept name="Functions Performed By Cells">
        <questions>
            <question>What functions do cells perform?</question>
            <question>How do cells contribute to the organism's survival?</question>
        </questions>
        <keywords>
            <keyword>cell</keyword>
            <keyword>function</keyword>
        </keywords>
        <prerequisites>
            <prerequisite>basic biology</prerequisite>
            <prerequisite>cells</prerequisite>
        </prerequisites>
        <content><![CDATA[Cells perform various functions necessary for the organism's survival...]]></content>
    </concept>"""

    # Generate actual XML string using the custom serialization function
    actual_elem = concept.to_xml()
    actual_xml = etree_to_string(actual_elem, cdata_tags={"content"})

    # Remove whitespace and newlines for comparison
    expected_xml_clean = "".join(expected_xml.strip().split())
    actual_xml_clean = "".join(actual_xml.strip().split())

    # Assert that the actual XML matches the expected XML
    assert (
        expected_xml_clean == actual_xml_clean
    ), "Concept XML string does not match expected output."


def test_topic_to_xml():
    concept = Concept(
        name="Functions Performed By Cells",
        keywords=["cell", "function"],
        questions=[
            "What functions do cells perform?",
            "How do cells contribute to the organism's survival?",
        ],
        prerequisites=["basic biology", "cells"],
        content="Cells perform various functions necessary for the organism's survival...",
    )
    topic = Topic(
        name="Cell Function",
        topic_summary="Cells have a wide range of functions...",
        concepts=[concept],
    )

    expected_xml = """<topic name="Cell Function">
        <topic_summary><![CDATA[Cells have a wide range of functions...]]></topic_summary>
        <concepts>
            <concept name="Functions Performed By Cells">
                <questions>
                    <question>What functions do cells perform?</question>
                    <question>How do cells contribute to the organism's survival?</question>
                </questions>
                <keywords>
                    <keyword>cell</keyword>
                    <keyword>function</keyword>
                </keywords>
                <prerequisites>
                    <prerequisite>basic biology</prerequisite>
                    <prerequisite>cells</prerequisite>
                </prerequisites>
                <content><![CDATA[Cells perform various functions necessary for the organism's survival...]]></content>
            </concept>
        </concepts>
    </topic>"""

    # Generate actual XML string using the custom serialization function
    actual_elem = topic.to_xml()
    actual_xml = etree_to_string(actual_elem, cdata_tags={"topic_summary", "content"})

    # Remove whitespace and newlines for comparison
    expected_xml_clean = "".join(expected_xml.strip().split())
    actual_xml_clean = "".join(actual_xml.strip().split())

    # Assert that the actual XML matches the expected XML
    assert (
        expected_xml_clean == actual_xml_clean
    ), "Topic XML string does not match expected output."


def test_domain_to_xml():
    concept = Concept(
        name="Functions Performed By Cells",
        keywords=["cell", "function"],
        questions=[
            "What functions do cells perform?",
            "How do cells contribute to the organism's survival?",
        ],
        prerequisites=["basic biology", "cells"],
        content="Cells perform various functions necessary for the organism's survival...",
    )
    topic = Topic(
        name="Cell Function",
        topic_summary="Cells have a wide range of functions...",
        concepts=[concept],
    )
    domain = Domain(
        name="Cell Biology",
        summary="Cells are the basic units of life...",
        topics=[topic],
    )

    expected_xml = """<domain name="Cell Biology">
        <summary><![CDATA[Cells are the basic units of life...]]></summary>
        <topic name="Cell Function">
            <topic_summary><![CDATA[Cells have a wide range of functions...]]></topic_summary>
            <concepts>
                <concept name="Functions Performed By Cells">
                    <questions>
                        <question>What functions do cells perform?</question>
                        <question>How do cells contribute to the organism's survival?</question>
                    </questions>
                    <keywords>
                        <keyword>cell</keyword>
                        <keyword>function</keyword>
                    </keywords>
                    <prerequisites>
                        <prerequisite>basic biology</prerequisite>
                        <prerequisite>cells</prerequisite>
                    </prerequisites>
                    <content><![CDATA[Cells perform various functions necessary for the organism's survival...]]></content>
                </concept>
            </concepts>
        </topic>
    </domain>"""

    # Generate actual XML string using the custom serialization function
    actual_elem = domain.to_xml()
    actual_xml = etree_to_string(
        actual_elem, cdata_tags={"summary", "topic_summary", "content"}
    )

    # Remove whitespace and newlines for comparison
    expected_xml_clean = "".join(expected_xml.strip().split())
    actual_xml_clean = "".join(actual_xml.strip().split())

    # Assert that the actual XML matches the expected XML
    assert (
        expected_xml_clean == actual_xml_clean
    ), "Domain XML string does not match expected output."


def test_domain_to_xml_string():
    concept = Concept(
        name="Functions Performed By Cells",
        keywords=["cell", "function"],
        questions=[
            "What functions do cells perform?",
            "How do cells contribute to the organism's survival?",
        ],
        prerequisites=["basic biology", "cells"],
        content="Cells perform various functions necessary for the organism's survival...",
    )
    topic = Topic(
        name="Cell Function",
        topic_summary="Cells have a wide range of functions...",
        concepts=[concept],
    )
    domain = Domain(
        name="Cell Biology",
        summary="Cells are the basic units of life...",
        topics=[topic],
    )

    expected_xml = """<domain name="Cell Biology">
<summary><![CDATA[Cells are the basic units of life...]]></summary>
<topic name="Cell Function">
<topic_summary><![CDATA[Cells have a wide range of functions...]]></topic_summary>
<concepts>
<concept name="Functions Performed By Cells">
<questions>
<question>What functions do cells perform?</question>
<question>How do cells contribute to the organism's survival?</question>
</questions>
<keywords>
<keyword>cell</keyword>
<keyword>function</keyword>
</keywords>
<prerequisites>
<prerequisite>basic biology</prerequisite>
<prerequisite>cells</prerequisite>
</prerequisites>
<content><![CDATA[Cells perform various functions necessary for the organism's survival...]]></content>
</concept>
</concepts>
</topic>
</domain>"""

    # Generate actual XML string
    actual_xml = domain.to_xml_string()

    # Remove whitespace for comparison
    expected_xml_stripped = "".join(expected_xml.strip().split())
    actual_xml_stripped = "".join(actual_xml.strip().split())

    # Assert that the strings are equal
    assert (
        expected_xml_stripped == actual_xml_stripped
    ), "Domain XML string does not match expected output."
