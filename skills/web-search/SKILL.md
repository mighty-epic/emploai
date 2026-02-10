---
name: web-search
description: Research and web browsing workflows using the browser/automation tools. Use when the task requires finding or verifying information on websites.
---

# Web Search

Use this skill when you need to search the web, verify facts on a website, or navigate web pages.

## When to Use

- Finding official documentation or release notes
- Verifying facts from authoritative sources
- Extracting information from web pages
- Navigating websites with complex UI

## How to Use

### Quick checks (lightweight)

If the answer can be derived from local files or existing context, prefer local sources first.

### Browser automation

When live browsing is required, use the browser/automation tools. In this Telegram agent:

- Use **/task** for multi-step browsing that requires interaction or authentication.
- In **auto mode**, the agent can directly call browser tools during chat.

### Reliable citation flow

1. Navigate to the official source
2. Extract the relevant text (copy exact wording where needed)
3. Summarize and attribute the source clearly

## Output format

When reporting web findings:

- Cite the source domain
- Quote short phrases for precision
- Summarize in plain language

Example:

"According to docs.example.com, the API requires an `Authorization` header with a bearer token. This is stated in the Authentication section of the API reference."
