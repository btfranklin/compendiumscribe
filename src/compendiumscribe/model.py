from __future__ import annotations
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET


@dataclass
class Concept:
    name: str
    keywords: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    content: str = ""

    def to_xml(self) -> ET.Element:
        concept_elem = ET.Element("concept", attrib={"name": self.name})

        # Add questions
        if self.questions:
            questions_elem = ET.SubElement(concept_elem, "questions")
            for question in self.questions:
                question_elem = ET.SubElement(questions_elem, "question")
                question_elem.text = question

        # Add keywords
        if self.keywords:
            keywords_elem = ET.SubElement(concept_elem, "keywords")
            for keyword in self.keywords:
                keyword_elem = ET.SubElement(keywords_elem, "keyword")
                keyword_elem.text = keyword

        # Add prerequisites
        if self.prerequisites:
            prerequisites_elem = ET.SubElement(concept_elem, "prerequisites")
            for prerequisite in self.prerequisites:
                prerequisite_elem = ET.SubElement(prerequisites_elem, "prerequisite")
                prerequisite_elem.text = prerequisite

        # Add content
        if self.content:
            content_elem = ET.SubElement(concept_elem, "content")
            content_elem.text = (
                self.content
            )  # CDATA will be handled during serialization

        return concept_elem


@dataclass
class Topic:
    name: str
    topic_summary: str = ""
    concepts: list[Concept] = field(default_factory=list)

    def to_xml(self) -> ET.Element:
        topic_elem = ET.Element("topic", attrib={"name": self.name})

        # Add topic summary
        if self.topic_summary:
            topic_summary_elem = ET.SubElement(topic_elem, "topic_summary")
            topic_summary_elem.text = (
                self.topic_summary
            )  # CDATA will be handled during serialization

        # Add concepts
        if self.concepts:
            concepts_elem = ET.SubElement(topic_elem, "concepts")
            for concept in self.concepts:
                concept_elem = concept.to_xml()
                concepts_elem.append(concept_elem)

        return topic_elem


@dataclass
class Domain:
    name: str
    summary: str = ""
    topics: list[Topic] = field(default_factory=list)

    def to_xml(self) -> ET.Element:
        domain_elem = ET.Element("domain", attrib={"name": self.name})

        # Add summary
        if self.summary:
            summary_elem = ET.SubElement(domain_elem, "summary")
            summary_elem.text = (
                self.summary
            )  # CDATA will be handled during serialization

        # Add topics
        if self.topics:
            for topic in self.topics:
                topic_elem = topic.to_xml()
                domain_elem.append(topic_elem)

        return domain_elem

    def to_xml_string(self) -> str:
        domain_elem = self.to_xml()
        cdata_tags = {"summary", "topic_summary", "content"}
        return etree_to_string(domain_elem, cdata_tags=cdata_tags)


def etree_to_string(elem, cdata_tags=None):
    from xml.sax.saxutils import escape

    if cdata_tags is None:
        cdata_tags = set()

    def serialize_element(e):
        tag = e.tag
        attrib = e.attrib
        attrib_str = " ".join(f'{k}="{escape(v)}"' for k, v in attrib.items())
        if attrib_str:
            s = f"<{tag} {attrib_str}>"
        else:
            s = f"<{tag}>"

        # Handle text content
        if e.text:
            if tag in cdata_tags:
                s += f"<![CDATA[{e.text}]]>"
            else:
                s += escape(e.text)

        # Serialize child elements
        for child in e:
            s += serialize_element(child)
            # Handle tail text (if any)
            if child.tail:
                s += escape(child.tail)

        # Close the tag
        s += f"</{tag}>"
        return s

    return serialize_element(elem)
