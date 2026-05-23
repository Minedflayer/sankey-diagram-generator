<div align="center">
  <h1>📊 AI Sankey Diagram Generator</h1>
  <p><em>Transform unstructured financial documents into interactive, structured flow diagrams using LLMs.</em></p>
</div>

[streamlit-app-2026-05-23-15-03-03.webm](https://github.com/user-attachments/assets/e6f46bd8-372b-4c4d-8a1f-592d23b7a416)

An intelligent web application built with Streamlit that automates the extraction of complex financial hierarchies from raw PDFs (like Income Statements and 10-K reports). By leveraging the speed of the Groq API, it parses unstructured text into strict JSON schemas and renders them dynamically as interactive Plotly Sankey diagrams.

## Features

- **Intelligent PDF Parsing:** Utilizes `PyMuPDF` to extract raw text while preserving tabular structures.
- **LLM-Powered Extraction:** Connects to Groq (LLaMA 3, Mixtral) to perform semantic data extraction and strict JSON formatting without fragile RegEx rules.
- **Interactive Visualization:** Renders center-origin Sankey diagrams via `Plotly`, mapping revenue streams and operating expenses with visual tiering and color coding.
- **Responsive UI:** Clean, minimalist Streamlit interface with configurable model parameters and execution transparency.

## Architecture

The application pipeline operates in three distinct phases:
1. **Ingestion:** A document is uploaded and parsed into clean, standardized plaintext.
2. **Structuring:** A highly restrictive system prompt forces the LLM to map the text into a predefined accounting skeleton (Revenue -> Gross Profit -> Operating Income).
3. **Rendering:** The JSON tree is recursively parsed into downstream/upstream edges, establishing spatial tiers and rendering the final Plotly graph.

## Prerequisites

- **Node.js / Python:** Python 3.10 or higher.
- **API Keys:** A valid [Groq API Key](https://console.groq.com/keys) for LLM access.

## Getting Started

### 1. Local Setup

Clone the repository and navigate into the project directory:

```bash
git clone [https://github.com/your-username/sankey-diagram-generator.git](https://github.com/your-username/sankey-diagram-generator.git)
cd sankey-diagram-generator

```


Create and activate a virtual environment:

```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

Install the required dependencies:

```bash
pip install -r requirements.txt

```

### 2. Environment configuration

Create a .env file in the root directory (or use Streamlit's .streamlit/secrets.toml locally) and add your API key:

```bash
GROQ_API_KEY="your_actual_api_key_here"

```

### 3. Running the Application
```bash
streamlit run app.py

```
