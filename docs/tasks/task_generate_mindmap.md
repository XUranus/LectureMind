# Task: task_generate_mindmap

## Overview

Generates a hierarchical knowledge mindmap from the lecture's sections and knowledge points using the LLM. The mindmap is stored as both a raw tree structure and pre-computed React Flow nodes/edges for frontend visualization.

**Position in DAG:** Task 9 (final task, depends on T8: task_coarse_grained_summary)

## Input

```json
{
  "video_id": "uuid-string",
  "summary_created": true
}
```

## Output

```json
{
  "video_id": "uuid-string",
  "mindmap_nodes": 18,
  "mindmap_edges": 17
}
```

## Processing Steps

### Step 1: Data Gathering

Same as coarse summary -- queries sections and knowledge points.

### Step 2: Prompt Construction

Builds a section-and-KP listing, but more compact (KP titles only, with key terms):

```
Section 1: Introduction to ML (00:00-05:30)
  - Supervised Learning (classification, regression)
  - Feature Engineering (normalization, encoding)
```

Truncated at 5000 characters.

### Step 3: LLM Call

Uses `MINDMAP_PROMPT` template with:
- Temperature: 0.4 (slightly higher for creative structure)
- Max tokens: 3000
- Model: default

### Step 4: Tree-to-React-Flow Conversion

The LLM returns a JSON tree. The `_tree_to_react_flow()` function converts it to React Flow format:

**Layout algorithm:**
- Top-down layout starting from root at (400, 0)
- Each level gets decreasing horizontal spacing (280px at root, less at deeper levels)
- Children are centered under their parent
- Vertical spacing: 120px per level

**Node styling by level:**

| Level | Background | Font | Purpose |
|-------|-----------|------|---------|
| 0 (root) | Indigo #4F46E5 | 16px bold | Lecture title |
| 1 (topics) | Purple #7C3AED | 14px semibold | Main topic branches |
| 2 (subtopics) | Blue #2563EB | 13px medium | Subtopic concepts |
| 3+ (details) | Gray #F3F4F6 | 12px normal | Specific details |

**Edge styling:**
- Type: `smoothstep` (curved connections)
- Root-level edges are animated (dashed moving line)
- Color: Slate gray #94A3B8

### Step 5: Persistence

Saved as `KnowledgeMindmap` record with three fields:
- `tree_data`: The raw hierarchical JSON tree from LLM
- `react_flow_nodes`: Pre-computed node array with positions and styles
- `react_flow_edges`: Pre-computed edge array with connection info

## LLM Output Schema (Tree)

```json
{
  "id": "root",
  "label": "Introduction to Machine Learning",
  "children": [
    {
      "id": "topic-supervised",
      "label": "Supervised Learning",
      "children": [
        {"id": "sub-classification", "label": "Classification", "children": []},
        {"id": "sub-regression", "label": "Regression", "children": []}
      ]
    },
    {
      "id": "topic-unsupervised",
      "label": "Unsupervised Learning",
      "children": [
        {"id": "sub-clustering", "label": "Clustering", "children": []}
      ]
    }
  ]
}
```

**Rules enforced in the prompt:**
- Max depth: 4 levels
- 2-6 main topic branches
- 1-5 subtopics per branch
- Unique IDs using descriptive slugs
- Conceptual grouping (not chronological)

## Fallback Behavior

If the LLM call fails, a fallback tree is auto-generated from the section/KP structure:

```
root: <Video Title>
  ├── section-0: <Section 0 Title>
  │     ├── <KP1 title>
  │     └── <KP2 title>
  ├── section-1: <Section 1 Title>
  ...
```

This is purely chronological but ensures the mindmap tab always has content.

## Database Models Affected

| Model | Operation |
|-------|-----------|
| `KnowledgeMindmap` | Create or Update (1:1 with Video) |

## Frontend Display

The mindmap is rendered using **@xyflow/react** (React Flow) in the **Mindmap** tab:
- Interactive pan/zoom
- Minimap for navigation
- Dotted grid background
- Nodes are draggable
- Fit-to-view on load
