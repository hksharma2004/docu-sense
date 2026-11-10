# DocuSense: Easy Presentation Script

Use this as a simple speaking guide for the project demo. You do not have to memorize it:
understand each part, then explain it in your own words.

## 1. Explain the problem

**You can say:**

> Technical rules are often written in long documents. Those documents can also have
> several versions. When a person or an AI looks for an answer, it can find the wrong
> version, lose the exact section where the answer came from, or quote text that does
> not match the original document. It can also miss a conflict between a company policy
> and a technical standard.
>
> This matters because we need to check where an answer came from, not just trust that
> it sounds correct.

The main problems DocuSense addresses are:

- The answer may come from an old or replaced version of a document.
- It may be hard to find the exact section or page that supports an answer.
- A quote may not match the source text anymore.
- A search for exact words may miss a useful result written in different words, while a
  meaning-based search may not find an exact technical term.
- A policy may disagree with a standard, and that disagreement may be easy to overlook.

## 2. Explain the solution

**You can say:**

> DocuSense reads PDF and Markdown documents and organizes them into sections and smaller
> pieces of text. We call each piece a span. For every span, DocuSense records which
> version it came from, where it appears, and a hash that can be checked later.
>
> Then we can search the documents, compare their versions, find possible conflicts,
> and show the evidence to a person or an AI assistant.

In simple terms:

- The web viewer is for people.
- MCP tools let compatible AI applications ask DocuSense for document information.
- Both use the same underlying document data and can point back to the same evidence.

## 3. Show the project

Follow these steps during the demo. Explain each screen as you open it.

### Step 1: Documents and versions

Open the Documents screen.

**You can say:**

> This screen lists the documents in the project. Some documents have more than one
> version. We keep the old versions instead of replacing them, so we can still check
> what changed and which version a piece of evidence came from.

### Step 2: Search

Search for **`maximum text line length`**, then open one of the results.

**You can say:**

> Here I am searching the documents. This result shows the text that matched, along with
> its citation, section, and page. The citation helps us go back to the exact place in
> the source.

### Step 3: Inspect and verify evidence

Open or select the result's span so its evidence details appear.

**You can say:**

> This is the evidence behind the search result. It includes details about where the
> text came from and a SHA-256 hash. DocuSense can check the text against the stored
> source data. This helps us detect if the evidence has changed.

### Step 4: Compare versions

Open the comparison for **`mail-policy`**, and compare **v1** with **v2**.

**You can say:**

> This view compares two versions of the same policy. In this example, the line-length
> rule changes from 2000 octets in v1 to 1000 octets in v2. The point is that we can see
> the change instead of treating the document as if it never changed.

### Step 5: Show possible contradictions

Open the Contradictions screen and show both sides of one result.

**You can say:**

> This result shows two statements that may disagree: one from a policy and one from an
> RFC. DocuSense shows both pieces of evidence so a person can review them. It does not
> silently decide which statement is correct or which source should take priority.

**Important:** The example policies are fictional test documents. They were written to
contain disagreements with RFCs so the contradiction feature can be demonstrated. They
are not real organizational policies.

### Step 6: Show the MCP tools

In MCP Inspector, call `list_documents`, then `search`. Open a search result with
`get_evidence` or check it with `verify_span`.

**You can say:**

> The website is one way to use DocuSense. These MCP tools let a compatible AI
> application ask for the same document information. For example, it can search for
> evidence, inspect a passage, and check its hash before using it in an answer.

## 4. Explain what happens behind the scenes

Use this section if your supervisors ask how the project works internally.

### Step 1: The manifest lists the documents

**You can say:**

> First, a manifest file tells the system which documents to load, where their files are,
> and which versions belong to each document.

### Step 2: The parser reads each file

**You can say:**

> The parser reads a PDF or Markdown file and turns it into consistent text. It also
> identifies sections and smaller text pieces called spans.

### Step 3: The project stores the text and its details

**You can say:**

> The original file and the cleaned text are stored using their content hashes. The
> database stores information such as document versions, sections, spans, and extracted
> facts. A span keeps its position in the text, so we can link back to its source.

### Step 4: The project extracts useful information

**You can say:**

> DocuSense looks for things like references to other documents, definitions, and
> sentences that state requirements or numeric limits. These steps are deterministic by
> default, which means they use fixed rules rather than asking an AI model every time.
> Optional AI assistance exists, but it is off by default.

### Step 5: The project builds search indexes

**You can say:**

> We use two kinds of search. BM25 is useful when the query contains exact words or
> technical names. Dense search uses embeddings to find text with a similar meaning,
> even if it uses different words. Hybrid search combines the two sets of results using
> reciprocal-rank fusion, which brings together their rankings.

### Step 6: The API and MCP share the same service

**You can say:**

> The main DocuSense service contains the document operations. The REST API uses it for
> the website, and the MCP server uses it to provide tools for AI applications. This
> means the website and MCP tools use the same underlying logic.

### Step 7: The viewer displays the results

**You can say:**

> Finally, the web viewer displays the documents, search results, evidence, possible
> contradictions, and version comparisons in a form that people can inspect.

## 5. Short closing summary

> DocuSense helps people and compatible AI applications find evidence in long,
> versioned technical documents. It keeps track of which version and passage an answer
> came from, lets us check the stored text, and makes changes and possible conflicts
> easier to review.
