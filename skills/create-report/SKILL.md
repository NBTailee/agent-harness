---
name: create-report
description: Create structured, professional reports from user-provided information, research, or analysis. Use when the user asks to write, draft, or generate a report.
---

# Create Report Skill

## Purpose

This skill provides instructions for creating clear, accurate, and well-structured reports based on the user's requirements and available information.

## When to Use

Use this skill when the user asks to:
- Create a report from provided information.
- Summarize findings into a formal report.
- Analyze data and present conclusions.
- Generate a project, research, business, or technical report.
- Turn notes or raw data into a professional document.

## Instructions

### Step 1: Understand the Request

Identify the following information:

- **Report topic:** What is the report about?
- **Purpose:** Why is the report being created?
- **Audience:** Who will read it?
- **Report type:** Business, technical, research, project, or general.
- **Scope:** What information should be included?
- **Output format:** Markdown, plain text, or another supported format.

If essential information is missing, ask the user for clarification. Otherwise, make reasonable assumptions and proceed.

### Step 2: Gather Information

Use the information provided by the user as the primary source.

If the task requires external research and browsing tools are available:
1. Search for relevant, reliable sources.
2. Verify important facts.
3. Distinguish verified facts from assumptions.
4. Record source titles, publication dates, and URLs when appropriate.
5. Never invent statistics, quotations, references, or research findings.

If the user provides files and file-reading tools are available, inspect relevant files before drafting the report.

### Step 3: Create the Report Structure

Use the following structure when appropriate:

1. **Title** — A concise description of the report.
2. **Executive Summary** — The main findings and recommendations.
3. **Introduction** — Background, purpose, and scope.
4. **Methodology** — How information was collected or analyzed, if applicable.
5. **Findings** — The key facts, observations, and results.
6. **Analysis and Discussion** — Interpretation of the findings.
7. **Recommendations** — Actionable next steps supported by the analysis.
8. **Conclusion** — A summary of the main takeaways.
9. **References** — Sources used to create the report, when applicable.

Adapt the structure to the report type. Do not include irrelevant sections simply to fill out the template.

### Step 4: Write the Report

Follow these writing principles:

- Use professional, clear, and objective language.
- Organize information with descriptive headings.
- Keep paragraphs focused on one main idea.
- Use bullet points for lists and tables for structured comparisons.
- Explain technical terminology when the intended audience may not know it.
- Support conclusions with evidence.
- Clearly label estimates, assumptions, and limitations.
- Avoid repetition and unnecessary filler.
- Do not invent missing information.

### Step 5: Review the Report

Before returning the report, verify that:

- The report addresses the user's original request.
- The structure is logical and easy to follow.
- Facts and figures are consistent with the available evidence.
- Recommendations follow from the findings.
- Important limitations and assumptions are disclosed.
- References are accurate and correspond to sources actually consulted.
- Grammar, spelling, and formatting are correct.

### Step 6: Deliver the Report

Return the completed report in the requested format.

If the user requests a Markdown report, provide a complete Markdown document.

If the user requests a downloadable file, use an available file-generation tool to create it. Do not claim that a file has been created unless it actually exists.

## Default Report Template

When the user does not specify a structure, use this template:

# [Report Title]

**Date:** [Current date, if relevant]  
**Author:** [Author, if provided]  
**Report Type:** [Report type]

## 1. Executive Summary

Summarize the report's purpose, major findings, and most important recommendations.

## 2. Introduction

Explain the background, objectives, and scope of the report.

## 3. Findings

Present the main findings using evidence, examples, tables, or other appropriate formats.

## 4. Analysis

Interpret the findings, explain their implications, and discuss relevant limitations.

## 5. Recommendations

List specific, actionable recommendations in order of priority where appropriate.

## 6. Conclusion

Summarize the key takeaways and their implications.

## 7. References

List the sources actually used, if applicable.

## Output Requirements

- Default format: Markdown.
- Default tone: Professional and objective.
- Default language: Match the user's language.
- Default detail level: Moderate, unless the user requests otherwise.
- Use tables only when they improve readability.
- Omit sections that are unnecessary for the requested report.
- Never fabricate facts, data, or citations.