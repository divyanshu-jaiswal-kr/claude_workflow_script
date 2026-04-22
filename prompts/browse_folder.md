# PIF Browse Folder — Confluence Space Explorer

You are running an automated workflow. Follow every step in order. Do not stop for clarification.

## Configuration

- **cloudId**: `CLOUD_ID_PLACEHOLDER`
- **space**: `SPACE_PLACEHOLDER`
- **parentId**: `COMMAND_PAGE_PARENT_ID_PLACEHOLDER`
- **today**: `TODAY_PLACEHOLDER`

---

## Step 1 — Determine parent page

Read `state/execution_plan.json` using the Read tool if it exists. Extract `config.create_page_parent` as the parent to explore (default: `COMMAND_PAGE_PARENT_ID_PLACEHOLDER`).

Print: `→ [1/3] Browsing under page ID: {parentId}`

---

## Step 2 — List child pages

Call `getConfluencePageDescendants`:
```
cloudId: CLOUD_ID_PLACEHOLDER
pageId: {parentId from step 1}
limit: 30
```

For each child page returned, record: `id`, `title`.

Then for up to 10 of the most recently created/modified pages, fetch a brief excerpt. For each of those 10, call `getConfluencePage`:
```
cloudId: CLOUD_ID_PLACEHOLDER
pageId: {child page id}
contentFormat: markdown
```
Extract the first 150 characters of the body (trimmed). Record `title`, `id`, first 150 chars.

Print: `→ [2/3] Found {count} pages. Fetched excerpts for top 10.`

---

## Step 3 — Print summary

Print a structured summary to the terminal:

```
📁 API Program Space (apiprogram)
   Parent page: {parent page title} (ID: {parentId})
   Child pages: {total count found}

Pages:
  1. 📄 {Page Title}
     ID: {id}
     URL: https://kroger.atlassian.net/wiki/spaces/apiprogram/pages/{id}
     Preview: {first 150 chars of body, or "(no content)"}

  2. 📄 {Page Title}
     ...
```

After listing all pages, print a one-paragraph summary:
```
Summary: The {space name} space contains {N} pages under this parent. Topics covered include: {comma-separated list of page title themes}. Most recent additions appear to cover {brief description based on titles and excerpts}.
```

Print: `✅ Browse complete. {count} pages listed.`
